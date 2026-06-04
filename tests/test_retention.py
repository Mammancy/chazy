import os
import tempfile
import unittest
from datetime import date, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config.settings import get_settings
from app.database.session import get_db
from app.main import create_application
from app.models import Base, RetentionState, SpeakingChallenge, SpeakingChallengeCompletion


class RetentionTests(unittest.TestCase):
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
            f"sqlite:///{os.path.join(self.temp_dir.name, 'retention-test.db')}",
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

    def test_retention_summary_returns_missions_goals_and_checkin(self):
        auth = self._sign_up()
        response = self.client.get("/api/v1/retention/summary", headers=self._auth_header(auth))

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(len(body["daily_missions"]), 3)
        self.assertEqual(len(body["weekly_goals"]), 3)
        self.assertEqual(body["daily_checkin"]["message"], "Welcome back")
        self.assertGreaterEqual(body["level"], 1)
        self.assertIn("freeze_tokens", body)

    def test_streak_freeze_protects_one_missed_day(self):
        auth = self._sign_up("freeze-user@example.com")
        user_id = auth["user"]["id"]
        session_id = f"chazy-user-{user_id}"
        with self.SessionLocal() as db:
            challenge = SpeakingChallenge(
                difficulty="beginner",
                title="Freeze Test",
                prompt="Speak clearly.",
                suggested_duration_seconds=60,
                focus_area="confidence",
            )
            db.add(challenge)
            db.commit()
            db.refresh(challenge)
            db.add(
                SpeakingChallengeCompletion(
                    challenge_id=challenge.id,
                    client_session_id=session_id,
                    user_id=user_id,
                    difficulty="beginner",
                    challenge_date=date.today() - timedelta(days=2),
                    spoken_seconds=60,
                    reflection="Done.",
                )
            )
            db.add(RetentionState(user_id=user_id, freeze_tokens=1))
            db.commit()

        response = self.client.get(
            "/api/v1/speaking-challenges/streak",
            params={"session_id": session_id},
            headers=self._auth_header(auth),
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertGreaterEqual(response.json()["current_streak"], 2)

        with self.SessionLocal() as db:
            state = db.query(RetentionState).filter(RetentionState.user_id == user_id).one()
            self.assertEqual(state.freeze_tokens, 0)
            self.assertEqual(state.last_freeze_used_date, date.today() - timedelta(days=1))

    def _sign_up(self, email: str = "retention-user@example.com") -> dict:
        response = self.client.post(
            "/api/v1/auth/signup",
            json={
                "full_name": "Retention User",
                "email": email,
                "phone_number": "08012345678",
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

