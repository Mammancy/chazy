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
from app.models import AdminAuditLog, Base, User


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

    def test_admin_login_redirects_to_setup_when_no_admin_exists(self):
        response = self.client.get("/admin/login", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/admin/setup")

    def test_first_admin_setup_creates_admin_and_then_locks_setup(self):
        setup = self.client.post(
            "/admin/setup",
            data={
                "full_name": "First Admin",
                "email": "first-admin@example.com",
                "phone_number": "08000000000",
                "country": "Nigeria",
                "state": "Kano",
                "password": "secret123",
            },
            follow_redirects=False,
        )
        self.assertEqual(setup.status_code, 303)
        self.assertEqual(setup.headers["location"], "/admin/dashboard")

        blocked_get = self.client.get("/admin/setup", follow_redirects=False)
        self.assertEqual(blocked_get.status_code, 303)
        self.assertEqual(blocked_get.headers["location"], "/admin/login")

        with self.SessionLocal() as db:
            admin = db.scalar(select(User).where(User.email == "first-admin@example.com"))
            self.assertIsNotNone(admin)
            self.assertEqual(admin.role, "admin")

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

    def test_admin_login_uses_local_http_cookies_without_secure_flag(self):
        self._sign_up("admin@example.com")
        response = self.client.post(
            "/admin/login",
            data={"email": "admin@example.com", "password": "secret123"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)

        set_cookie_headers = response.headers.get_list("set-cookie")
        admin_cookies = [header for header in set_cookie_headers if "chazy_admin_" in header]
        self.assertEqual(len(admin_cookies), 2)
        self.assertTrue(all("secure" not in header.lower() for header in admin_cookies))

    def test_admin_login_uses_secure_cookies_for_https_request(self):
        self._sign_up("admin@example.com")
        response = self.client.post(
            "https://testserver/admin/login",
            data={"email": "admin@example.com", "password": "secret123"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)

        set_cookie_headers = response.headers.get_list("set-cookie")
        admin_cookies = [header for header in set_cookie_headers if "chazy_admin_" in header]
        self.assertEqual(len(admin_cookies), 2)
        self.assertTrue(all("secure" in header.lower() for header in admin_cookies))

    def test_admin_login_uses_secure_cookies_in_production(self):
        self._sign_up("admin@example.com")
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "production",
                "JWT_SECRET_KEY": "a-unique-production-secret-with-48-characters!!",
                "ADMIN_EMAILS": "admin@example.com",
            },
        ):
            get_settings.cache_clear()
            response = self.client.post(
                "/admin/login",
                data={"email": "admin@example.com", "password": "secret123"},
                follow_redirects=False,
            )
        get_settings.cache_clear()
        self.assertEqual(response.status_code, 303)

        set_cookie_headers = response.headers.get_list("set-cookie")
        admin_cookies = [header for header in set_cookie_headers if "chazy_admin_" in header]
        self.assertEqual(len(admin_cookies), 2)
        self.assertTrue(all("secure" in header.lower() for header in admin_cookies))

    def test_existing_admin_can_create_additional_admin(self):
        self._sign_up("admin@example.com")
        login = self.client.post(
            "/admin/login",
            data={"email": "admin@example.com", "password": "secret123"},
            follow_redirects=False,
        )
        self.assertEqual(login.status_code, 303)
        csrf_token = self.client.cookies.get("chazy_admin_csrf")

        response = self.client.post(
            "/api/v1/admin/users/admins",
            json={
                "full_name": "Second Admin",
                "email": "second-admin@example.com",
                "phone_number": "08000000001",
                "country": "Nigeria",
                "state": "Lagos",
                "password": "secret123",
            },
            headers={"X-CSRF-Token": csrf_token},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["user"]["email"], "second-admin@example.com")

        login_second = self.client.post(
            "/admin/login",
            data={"email": "second-admin@example.com", "password": "secret123"},
            follow_redirects=False,
        )
        self.assertEqual(login_second.status_code, 303)

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
