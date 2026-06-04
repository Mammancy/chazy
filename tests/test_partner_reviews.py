import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config.settings import get_settings
from app.database.session import get_db
from app.main import create_application
from app.models import Base


class PartnerReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.env_patch = patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": "test-jwt-secret",
                "JWT_ACCESS_TOKEN_MINUTES": "30",
                "JWT_REFRESH_TOKEN_DAYS": "30",
            },
        )
        self.env_patch.start()
        get_settings.cache_clear()

        self.engine = create_engine(
            f"sqlite:///{os.path.join(self.temp_dir.name, 'partner-review-test.db')}",
            connect_args={"check_same_thread": False},
        )
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine, expire_on_commit=False)
        Base.metadata.create_all(bind=self.engine)

        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        self.app = create_application()
        self.app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(self.app)

    def tearDown(self):
        self.app.dependency_overrides.clear()
        self.client.close()
        self.engine.dispose()
        get_settings.cache_clear()
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_completed_session_can_be_reviewed_once_and_reputation_updates(self):
        first = self._sign_up("review-first@example.com", "Review First")
        second = self._sign_up("review-second@example.com", "Review Second")
        session = self._completed_session(first, second)

        review = self.client.post(
            f"/api/v1/practice-sessions/{session['id']}/review",
            json={"rating": 5, "comment": "Supportive partner with clear feedback."},
            headers=self._auth_header(first),
        )
        self.assertEqual(review.status_code, 200, review.text)
        self.assertEqual(review.json()["reviewed_user_id"], second["user"]["id"])
        self.assertEqual(review.json()["rating"], 5)

        duplicate = self.client.post(
            f"/api/v1/practice-sessions/{session['id']}/review",
            json={"rating": 4, "comment": "Trying again."},
            headers=self._auth_header(first),
        )
        self.assertEqual(duplicate.status_code, 400)

        reviews = self.client.get(
            f"/api/v1/speaking-partners/{second['user']['id']}/reviews",
            headers=self._auth_header(first),
        )
        self.assertEqual(reviews.status_code, 200, reviews.text)
        self.assertEqual(len(reviews.json()["reviews"]), 1)

        reputation = self.client.get(
            f"/api/v1/speaking-partners/{second['user']['id']}/reputation",
            headers=self._auth_header(first),
        )
        self.assertEqual(reputation.status_code, 200, reputation.text)
        body = reputation.json()
        self.assertEqual(body["average_rating"], 5.0)
        self.assertEqual(body["total_reviews"], 1)
        self.assertEqual(body["completed_sessions"], 1)
        self.assertEqual(body["reliability_score"], 100)
        self.assertEqual(body["repeat_partner_count"], 0)
        self.assertEqual(len(body["recent_reviews"]), 1)

    def test_review_requires_participant_and_completed_session(self):
        first = self._sign_up("review-rule-first@example.com", "Rule First")
        second = self._sign_up("review-rule-second@example.com", "Rule Second")
        third = self._sign_up("review-rule-third@example.com", "Rule Third")
        request = self._accepted_request(first, second)
        session = self._session(first, request)

        too_early = self.client.post(
            f"/api/v1/practice-sessions/{session['id']}/review",
            json={"rating": 5, "comment": "Too soon."},
            headers=self._auth_header(first),
        )
        self.assertEqual(too_early.status_code, 400)

        completed = self.client.patch(
            f"/api/v1/practice-sessions/{session['id']}/complete",
            json={"feedback": "Completed."},
            headers=self._auth_header(first),
        )
        self.assertEqual(completed.status_code, 200, completed.text)

        forbidden = self.client.post(
            f"/api/v1/practice-sessions/{session['id']}/review",
            json={"rating": 5, "comment": "Not my session."},
            headers=self._auth_header(third),
        )
        self.assertEqual(forbidden.status_code, 403)

    def _completed_session(self, first: dict, second: dict) -> dict:
        request = self._accepted_request(first, second)
        session = self._session(first, request)
        completed = self.client.patch(
            f"/api/v1/practice-sessions/{session['id']}/complete",
            json={"feedback": "Helpful practice."},
            headers=self._auth_header(first),
        )
        self.assertEqual(completed.status_code, 200, completed.text)
        return completed.json()

    def _session(self, auth: dict, request: dict) -> dict:
        created = self.client.post(
            "/api/v1/practice-sessions",
            json={
                "request_id": request["id"],
                "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                "duration_minutes": 30,
                "topic": "Partner review practice",
            },
            headers=self._auth_header(auth),
        )
        self.assertEqual(created.status_code, 200, created.text)
        return created.json()

    def _accepted_request(self, first: dict, second: dict) -> dict:
        self._public_profile(second)
        request = self.client.post(
            "/api/v1/speaking-partners/requests",
            json={"receiver_user_id": second["user"]["id"], "message": "Practice?"},
            headers=self._auth_header(first),
        )
        self.assertEqual(request.status_code, 200, request.text)
        accepted = self.client.patch(
            f"/api/v1/speaking-partners/requests/{request.json()['id']}",
            json={"status": "accepted"},
            headers=self._auth_header(second),
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        return accepted.json()

    def _public_profile(self, auth: dict) -> None:
        response = self.client.patch(
            "/api/v1/speaking-partners/me",
            json={"is_public": True, "target_language": "English"},
            headers=self._auth_header(auth),
        )
        self.assertEqual(response.status_code, 200, response.text)

    def _sign_up(self, email: str, full_name: str) -> dict:
        response = self.client.post(
            "/api/v1/auth/signup",
            json={
                "full_name": full_name,
                "email": email,
                "phone_number": f"081{abs(hash(email)) % 10000000:07d}",
                "country": "Nigeria",
                "state": "Kano",
                "password": "secret123",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    @staticmethod
    def _auth_header(auth_body: dict) -> dict[str, str]:
        return {"Authorization": f"Bearer {auth_body['access_token']}"}


if __name__ == "__main__":
    unittest.main()
