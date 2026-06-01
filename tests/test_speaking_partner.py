import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config.settings import get_settings
from app.database.session import get_db
from app.main import create_application
from app.models import Base


class SpeakingPartnerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
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
            f"sqlite:///{os.path.join(self.temp_dir.name, 'speaking-partner-test.db')}",
            connect_args={"check_same_thread": False},
        )
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
            expire_on_commit=False,
        )
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
        self.client.close()
        self.engine.dispose()
        get_settings.cache_clear()
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_profile_filters_and_requests(self):
        first = self._sign_up("partner-first@example.com", "First Partner")
        second = self._sign_up("partner-second@example.com", "Second Partner")

        first_profile = self.client.patch(
            "/api/v1/speaking-partners/me",
            json={
                "speaking_level": "beginner",
                "native_language": "Hausa",
                "target_language": "English",
                "interests": ["interviews", "daily conversation"],
                "timezone": "Africa/Lagos",
                "availability": {"weekdays": ["evening"]},
                "bio": "I want supportive conversation practice.",
                "is_public": True,
            },
            headers=self._auth_header(first),
        )
        self.assertEqual(first_profile.status_code, 200, first_profile.text)
        self.assertTrue(first_profile.json()["is_public"])

        second_profile = self.client.patch(
            "/api/v1/speaking-partners/me",
            json={
                "speaking_level": "intermediate",
                "native_language": "Arabic",
                "target_language": "English",
                "interests": ["presentations"],
                "timezone": "Africa/Lagos",
                "is_public": True,
            },
            headers=self._auth_header(second),
        )
        self.assertEqual(second_profile.status_code, 200, second_profile.text)

        filtered = self.client.get(
            "/api/v1/speaking-partners",
            params={"speaking_level": "intermediate", "interests": "presentations"},
            headers=self._auth_header(first),
        )
        self.assertEqual(filtered.status_code, 200, filtered.text)
        partners = filtered.json()["partners"]
        self.assertEqual(len(partners), 1)
        self.assertEqual(partners[0]["user_id"], second["user"]["id"])

        request = self.client.post(
            "/api/v1/speaking-partners/requests",
            json={
                "receiver_user_id": second["user"]["id"],
                "message": "Can we practice confident interview answers?",
            },
            headers=self._auth_header(first),
        )
        self.assertEqual(request.status_code, 200, request.text)
        request_body = request.json()
        self.assertEqual(request_body["status"], "pending")
        self.assertEqual(request_body["sender_user_id"], first["user"]["id"])

        accepted = self.client.patch(
            f"/api/v1/speaking-partners/requests/{request_body['id']}",
            json={"status": "accepted"},
            headers=self._auth_header(second),
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(accepted.json()["status"], "accepted")

        request_lists = self.client.get(
            "/api/v1/speaking-partners/requests",
            headers=self._auth_header(first),
        )
        self.assertEqual(request_lists.status_code, 200, request_lists.text)
        self.assertEqual(len(request_lists.json()["outgoing"]), 1)

    def test_rejects_self_and_cross_user_request_updates(self):
        first = self._sign_up("partner-self@example.com", "Self Partner")
        second = self._sign_up("partner-receiver@example.com", "Receiver Partner")

        self.client.patch(
            "/api/v1/speaking-partners/me",
            json={"is_public": True, "target_language": "English"},
            headers=self._auth_header(second),
        )

        self_request = self.client.post(
            "/api/v1/speaking-partners/requests",
            json={"receiver_user_id": first["user"]["id"], "message": "Practice?"},
            headers=self._auth_header(first),
        )
        self.assertEqual(self_request.status_code, 400)

        request = self.client.post(
            "/api/v1/speaking-partners/requests",
            json={"receiver_user_id": second["user"]["id"], "message": "Practice?"},
            headers=self._auth_header(first),
        )
        self.assertEqual(request.status_code, 200, request.text)

        forbidden = self.client.patch(
            f"/api/v1/speaking-partners/requests/{request.json()['id']}",
            json={"status": "accepted"},
            headers=self._auth_header(first),
        )
        self.assertEqual(forbidden.status_code, 403)

    def test_recommended_partners_are_scored_and_sorted(self):
        first = self._sign_up("match-first@example.com", "Match First")
        strong = self._sign_up("match-strong@example.com", "Strong Match")
        weak = self._sign_up("match-weak@example.com", "Weak Match")

        self.client.patch(
            "/api/v1/speaking-partners/me",
            json={
                "speaking_level": "intermediate",
                "native_language": "Hausa",
                "target_language": "English",
                "interests": ["technology", "business", "interviews"],
                "timezone": "Africa/Lagos",
                "availability": {"notes": "weekday evenings"},
                "is_public": True,
            },
            headers=self._auth_header(first),
        )
        self.client.patch(
            "/api/v1/speaking-partners/me",
            json={
                "speaking_level": "intermediate",
                "native_language": "English",
                "target_language": "English",
                "interests": ["technology", "business"],
                "timezone": "Africa/Lagos",
                "availability": {"notes": "weekday evenings"},
                "is_public": True,
            },
            headers=self._auth_header(strong),
        )
        self.client.patch(
            "/api/v1/speaking-partners/me",
            json={
                "speaking_level": "beginner",
                "native_language": "Arabic",
                "target_language": "French",
                "interests": ["travel"],
                "timezone": "America/Los_Angeles",
                "availability": {"notes": "weekend mornings"},
                "is_public": True,
            },
            headers=self._auth_header(weak),
        )

        recommended = self.client.get(
            "/api/v1/speaking-partners/recommended",
            headers=self._auth_header(first),
        )
        self.assertEqual(recommended.status_code, 200, recommended.text)
        partners = recommended.json()["partners"]
        self.assertEqual(partners[0]["user_id"], strong["user"]["id"])
        self.assertGreater(partners[0]["match_score"], partners[1]["match_score"])
        self.assertEqual(partners[0]["shared_interests"], ["technology", "business"])
        self.assertIn("Same target language", partners[0]["match_reasons"])
        self.assertIn("Similar speaking level", partners[0]["match_reasons"])
        self.assertIn("Compatible schedule", partners[0]["match_reasons"])

    def test_recommended_partners_empty_when_profile_incomplete(self):
        first = self._sign_up("match-incomplete@example.com", "Incomplete Match")
        second = self._sign_up("match-visible@example.com", "Visible Match")

        self.client.patch(
            "/api/v1/speaking-partners/me",
            json={"is_public": True, "target_language": "English"},
            headers=self._auth_header(second),
        )

        recommended = self.client.get(
            "/api/v1/speaking-partners/recommended",
            headers=self._auth_header(first),
        )
        self.assertEqual(recommended.status_code, 200, recommended.text)
        self.assertEqual(recommended.json()["partners"], [])

    def _sign_up(self, email: str, full_name: str) -> dict:
        response = self.client.post(
            "/api/v1/auth/signup",
            json={
                "full_name": full_name,
                "email": email,
                "phone_number": "08000000000",
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
