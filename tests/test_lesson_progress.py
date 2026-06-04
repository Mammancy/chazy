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


class LessonProgressTests(unittest.TestCase):
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
            f"sqlite:///{os.path.join(self.temp_dir.name, 'lesson-progress-test.db')}",
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
        self.client.close()
        self.engine.dispose()
        get_settings.cache_clear()
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_lesson_completion_is_persisted_and_idempotent(self):
        user = self._sign_up("lesson-progress@example.com")

        before = self.client.get(
            "/api/v1/lessons/beginner-foundations",
            headers=self._auth_header(user),
        )
        self.assertEqual(before.status_code, 200, before.text)
        self.assertFalse(before.json()["completed"])

        completed = self.client.post(
            "/api/v1/lessons/beginner-foundations/complete",
            headers=self._auth_header(user),
        )
        self.assertEqual(completed.status_code, 200, completed.text)
        body = completed.json()
        self.assertFalse(body["already_completed"])
        self.assertEqual(body["xp_awarded"], 120)
        self.assertTrue(body["lesson"]["completed"])
        self.assertEqual(body["lesson"]["progress"], 100)

        repeated = self.client.post(
            "/api/v1/lessons/beginner-foundations/complete",
            headers=self._auth_header(user),
        )
        self.assertEqual(repeated.status_code, 200, repeated.text)
        self.assertTrue(repeated.json()["already_completed"])
        self.assertEqual(repeated.json()["xp_awarded"], 0)

        courses = self.client.get("/api/v1/lessons/", headers=self._auth_header(user))
        self.assertEqual(courses.status_code, 200, courses.text)
        course = next(item for item in courses.json() if item["id"] == "beginner-foundations")
        self.assertTrue(course["completed"])
        self.assertEqual(course["progress"], 100)

    def test_lesson_progress_is_user_specific(self):
        first = self._sign_up("lesson-first@example.com")
        second = self._sign_up("lesson-second@example.com")

        completed = self.client.post(
            "/api/v1/lessons/beginner-foundations/complete",
            headers=self._auth_header(first),
        )
        self.assertEqual(completed.status_code, 200, completed.text)

        other = self.client.get(
            "/api/v1/lessons/beginner-foundations",
            headers=self._auth_header(second),
        )
        self.assertEqual(other.status_code, 200, other.text)
        self.assertFalse(other.json()["completed"])

    def _sign_up(self, email: str):
        response = self.client.post(
            "/api/v1/auth/signup",
            json={
                "full_name": email.split("@")[0].replace("-", " ").title(),
                "email": email,
                "phone_number": f"080{abs(hash(email)) % 10000000:07d}",
                "country": "Nigeria",
                "state": "Kano",
                "password": "secret123",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    @staticmethod
    def _auth_header(user):
        return {"Authorization": f"Bearer {user['access_token']}"}
