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


class AuthSettingsTests(unittest.TestCase):
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
            f"sqlite:///{os.path.join(self.temp_dir.name, 'auth-settings-test.db')}",
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

    def test_active_sessions_and_logout_all(self):
        auth = self._sign_up()

        sessions = self.client.get("/api/v1/auth/sessions", headers=self._auth_header(auth))
        self.assertEqual(sessions.status_code, 200, sessions.text)
        self.assertGreaterEqual(len(sessions.json()["sessions"]), 1)

        logged_out = self.client.post("/api/v1/auth/logout-all", headers=self._auth_header(auth))
        self.assertEqual(logged_out.status_code, 200, logged_out.text)

        sessions_after = self.client.get("/api/v1/auth/sessions", headers=self._auth_header(auth))
        self.assertEqual(sessions_after.status_code, 200, sessions_after.text)
        self.assertEqual(sessions_after.json()["sessions"], [])

    def test_change_password_requires_current_password(self):
        auth = self._sign_up()

        rejected = self.client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "wrong", "new_password": "newsecret123"},
            headers=self._auth_header(auth),
        )
        self.assertEqual(rejected.status_code, 400)

        changed = self.client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "secret123", "new_password": "newsecret123"},
            headers=self._auth_header(auth),
        )
        self.assertEqual(changed.status_code, 200, changed.text)

        old_login = self.client.post(
            "/api/v1/auth/signin",
            json={"email": "settings-user@example.com", "password": "secret123"},
        )
        self.assertEqual(old_login.status_code, 401)

        new_login = self.client.post(
            "/api/v1/auth/signin",
            json={"email": "settings-user@example.com", "password": "newsecret123"},
        )
        self.assertEqual(new_login.status_code, 200, new_login.text)

    def _sign_up(self):
        response = self.client.post(
            "/api/v1/auth/signup",
            json={
                "full_name": "Settings User",
                "email": "settings-user@example.com",
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

