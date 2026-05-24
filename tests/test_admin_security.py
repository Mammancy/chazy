import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.config.settings import get_settings
from app.database.session import get_db
from app.main import create_application
from app.models import AdminAuditLog, Base


class AdminSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.env_patch = patch.dict(
            os.environ,
            {
                "ADMIN_EMAILS": "admin@example.com",
                "JWT_SECRET_KEY": "test-jwt-secret",
            },
        )
        self.env_patch.start()
        get_settings.cache_clear()

        self.engine = create_engine(
            f"sqlite:///{os.path.join(self.temp_dir.name, 'admin-security.db')}",
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

    def test_admin_pages_redirect_to_login_without_session(self):
        response = self.client.get("/admin/dashboard", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/admin/login")

    def test_non_admin_cannot_access_admin_api(self):
        learner = self._sign_up("learner@example.com")
        response = self.client.get(
            "/api/v1/admin/analytics/dashboard",
            headers=self._auth_header(learner),
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_can_access_admin_api_with_bearer_token(self):
        admin = self._sign_up("admin@example.com")
        response = self.client.get(
            "/api/v1/admin/analytics/dashboard",
            headers=self._auth_header(admin),
        )
        self.assertEqual(response.status_code, 200)

    def test_admin_mutations_require_csrf_and_write_audit_log(self):
        admin = self._sign_up("admin@example.com")
        learner = self._sign_up("learner@example.com")
        login = self.client.post(
            "/admin/login",
            data={"email": "admin@example.com", "password": "secret123"},
            follow_redirects=False,
        )
        self.assertEqual(login.status_code, 303)
        csrf_token = self.client.cookies.get("chazy_admin_csrf")
        self.assertTrue(csrf_token)

        missing_csrf = self.client.patch(
            f"/api/v1/admin/users/{learner['user']['id']}/status",
            json={"is_active": False},
        )
        self.assertEqual(missing_csrf.status_code, 403)

        updated = self.client.patch(
            f"/api/v1/admin/users/{learner['user']['id']}/status",
            json={"is_active": False},
            headers={"X-CSRF-Token": csrf_token},
        )
        self.assertEqual(updated.status_code, 200)

        with self.SessionLocal() as db:
            audit_log = db.scalar(
                select(AdminAuditLog)
                .where(AdminAuditLog.action == "admin_user_status_updated")
                .order_by(AdminAuditLog.id.desc())
                .limit(1)
            )
            self.assertIsNotNone(audit_log)
            self.assertEqual(audit_log.admin_user_id, admin["user"]["id"])
            self.assertEqual(audit_log.target_id, learner["user"]["id"])

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
