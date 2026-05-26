import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.config.settings import get_settings
from app.database.session import get_db
from app.main import create_application
from app.models import Base, RefreshToken, User
from app.services.auth_service import AuthService


class AuthorizationBoundaryTests(unittest.TestCase):
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
            f"sqlite:///{os.path.join(self.temp_dir.name, 'auth-test.db')}",
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

    def test_login_issues_jwt_tokens_and_refreshes(self):
        user = self._sign_up("first@example.com")
        self.assertTrue(user["access_token"])
        self.assertTrue(user["refresh_token"])
        self.assertEqual(user["token_type"], "bearer")
        self.assertGreater(user["expires_in"], 0)

        login = self.client.post(
            "/api/v1/auth/signin",
            json={"email": "first@example.com", "password": "secret123"},
        )
        self.assertEqual(login.status_code, 200)
        login_body = login.json()
        self.assertTrue(login_body["access_token"])
        self.assertTrue(login_body["refresh_token"])

        refresh = self.client.post("/api/v1/auth/refresh", json={"refresh_token": login_body["refresh_token"]})
        self.assertEqual(refresh.status_code, 200)
        self.assertTrue(refresh.json()["access_token"])
        self.assertTrue(refresh.json()["refresh_token"])
        self.assertNotEqual(refresh.json()["refresh_token"], login_body["refresh_token"])

    def test_refresh_token_rotation_rejects_reuse_and_revokes_replacements(self):
        auth = self._sign_up("rotation@example.com")
        first_refresh_token = auth["refresh_token"]

        first_rotation = self.client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": first_refresh_token},
        )
        self.assertEqual(first_rotation.status_code, 200, first_rotation.text)
        second_refresh_token = first_rotation.json()["refresh_token"]
        self.assertNotEqual(second_refresh_token, first_refresh_token)

        reused = self.client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": first_refresh_token},
        )
        self.assertEqual(reused.status_code, 401)
        self.assertEqual(reused.json()["detail"], "Refresh token reuse detected.")

        revoked_replacement = self.client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": second_refresh_token},
        )
        self.assertEqual(revoked_replacement.status_code, 401)

        with self.SessionLocal() as db:
            records = db.scalars(select(RefreshToken).where(RefreshToken.user_id == auth["user"]["id"])).all()
            self.assertGreaterEqual(len(records), 2)
            self.assertTrue(all(record.revoked_at is not None for record in records))
            self.assertTrue(any(record.reuse_detected_at is not None for record in records))

    def test_password_reset_revokes_refresh_tokens(self):
        auth = self._sign_up("reset@example.com")
        reset_token = "reset-token-for-test"
        with self.SessionLocal() as db:
            user = db.scalar(select(User).where(User.email == "reset@example.com"))
            user.password_reset_token_hash = AuthService._hash_reset_token(reset_token)
            user.password_reset_expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
            db.add(user)
            db.commit()

        reset = self.client.post(
            "/api/v1/auth/reset-password",
            json={"token": reset_token, "new_password": "new-secret123"},
        )
        self.assertEqual(reset.status_code, 200, reset.text)

        rejected = self.client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": auth["refresh_token"]},
        )
        self.assertEqual(rejected.status_code, 401)

    def test_account_deletion_revokes_refresh_tokens(self):
        auth = self._sign_up("delete-me@example.com")
        deleted = self.client.delete(
            f"/api/v1/auth/profile/{auth['user']['id']}",
            headers=self._auth_header(auth),
        )
        self.assertEqual(deleted.status_code, 200, deleted.text)

        rejected = self.client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": auth["refresh_token"]},
        )
        self.assertEqual(rejected.status_code, 401)

    def test_profile_requires_authentication_and_rejects_other_user(self):
        first = self._sign_up("first@example.com")
        second = self._sign_up("second@example.com")

        unauthenticated = self.client.get(f"/api/v1/auth/profile/{first['user']['id']}")
        self.assertEqual(unauthenticated.status_code, 401)

        own_profile = self.client.get(
            f"/api/v1/auth/profile/{first['user']['id']}",
            headers=self._auth_header(first),
        )
        self.assertEqual(own_profile.status_code, 200)
        self.assertEqual(own_profile.json()["id"], first["user"]["id"])

        other_profile = self.client.get(
            f"/api/v1/auth/profile/{second['user']['id']}",
            headers=self._auth_header(first),
        )
        self.assertEqual(other_profile.status_code, 403)

        delete_other = self.client.delete(
            f"/api/v1/auth/profile/{second['user']['id']}",
            headers=self._auth_header(first),
        )
        self.assertEqual(delete_other.status_code, 403)

    def test_chat_history_uses_authenticated_user_not_query_user_id(self):
        first = self._sign_up("first@example.com")
        second = self._sign_up("second@example.com")

        response = self.client.get(
            "/api/v1/chat/history",
            params={"session_id": "spoofed-session", "user_id": second["user"]["id"]},
            headers=self._auth_header(first),
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["user_id"], first["user"]["id"])
        self.assertEqual(body["session_id"], f"chazy-user-{first['user']['id']}")

    def test_vocabulary_rejects_cross_user_entry_updates(self):
        first = self._sign_up("first@example.com")
        second = self._sign_up("second@example.com")

        created = self.client.post(
            "/api/v1/vocabulary-notebook/",
            json={
                "session_id": "spoofed-session",
                "user_id": first["user"]["id"],
                "word": "clear",
                "meaning": "easy to understand",
                "example_sentence": "Your explanation is clear.",
            },
            headers=self._auth_header(second),
        )
        self.assertEqual(created.status_code, 200)
        entry = created.json()
        self.assertEqual(entry["user_id"], second["user"]["id"])

        forbidden = self.client.patch(
            f"/api/v1/vocabulary-notebook/{entry['id']}",
            json={"meaning": "not allowed"},
            headers=self._auth_header(first),
        )
        self.assertEqual(forbidden.status_code, 403)

    def test_protected_user_endpoints_return_401_without_token(self):
        cases = [
            ("get", "/api/v1/chat/history", {"params": {"session_id": "x"}}),
            ("get", "/api/v1/vocabulary-notebook/", {"params": {"session_id": "x"}}),
            ("get", "/api/v1/speaking-challenges/daily", {"params": {"session_id": "x"}}),
            ("get", "/api/v1/learning-analytics/", {"params": {"session_id": "x"}}),
            ("get", "/api/v1/fluency-dashboard/", {"params": {"session_id": "x"}}),
        ]
        for method, path, kwargs in cases:
            with self.subTest(path=path):
                response = getattr(self.client, method)(path, **kwargs)
                self.assertEqual(response.status_code, 401)

    def _sign_up(self, email: str) -> dict:
        response = self.client.post(
            "/api/v1/auth/signup",
            json={
                "full_name": "Test User",
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
