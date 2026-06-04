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


class SpeakingEvaluationTests(unittest.TestCase):
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
            f"sqlite:///{os.path.join(self.temp_dir.name, 'speaking-evaluation-test.db')}",
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

    def test_speaking_evaluation_scores_and_history(self):
        auth = self._sign_up("eval-user@example.com", "Evaluation User")
        response = self.client.post(
            "/api/v1/speaking-evaluation",
            json={
                "transcript": "I goes to market. I speak clearly about my work and goals.",
                "duration_seconds": 35,
            },
            headers=self._auth_header(auth),
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertGreaterEqual(body["overall_score"], 1)
        self.assertLessEqual(body["overall_score"], 100)
        self.assertTrue(any(item["original"].lower() == "i goes" for item in body["corrections"]))
        self.assertTrue(body["strengths"])
        self.assertTrue(body["improvements"])
        self.assertIn("coach_feedback", body)

        history = self.client.get(
            "/api/v1/speaking-evaluation/history",
            headers=self._auth_header(auth),
        )
        self.assertEqual(history.status_code, 200, history.text)
        history_body = history.json()
        self.assertEqual(history_body["evaluations_completed"], 1)
        self.assertEqual(history_body["best_speaking_score"], body["overall_score"])
        self.assertEqual(len(history_body["evaluations"]), 1)

    def test_speaking_evaluation_requires_auth_and_valid_payload(self):
        unauthorized = self.client.post(
            "/api/v1/speaking-evaluation",
            json={"transcript": "Hello", "duration_seconds": 10},
        )
        self.assertEqual(unauthorized.status_code, 401)

        auth = self._sign_up("eval-invalid@example.com", "Invalid Eval")
        invalid = self.client.post(
            "/api/v1/speaking-evaluation",
            json={"transcript": "", "duration_seconds": 0},
            headers=self._auth_header(auth),
        )
        self.assertEqual(invalid.status_code, 422)

    def _sign_up(self, email: str, full_name: str) -> dict:
        response = self.client.post(
            "/api/v1/auth/signup",
            json={
                "full_name": full_name,
                "email": email,
                "phone_number": f"082{abs(hash(email)) % 10000000:07d}",
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
