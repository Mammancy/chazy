import os
import tempfile
import unittest
from datetime import timezone
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.config.settings import get_settings
from app.database.session import get_db
from app.main import create_application
from app.models import Base, User
from app.services.auth_service import AuthService
from app.services.email_service import EmailService
from app.services.startup_validation import validate_smtp_startup_configuration


SMTP_ENV = {
    "SMTP_HOST": "smtp.gmail.com",
    "SMTP_PORT": "587",
    "SMTP_USERNAME": "learner@example.com",
    "SMTP_PASSWORD": "gmail-app-password-for-tests",
    "SMTP_FROM_EMAIL": "learner@example.com",
    "SMTP_USE_TLS": "true",
    "SMTP_USE_SSL": "false",
    "SMTP_TIMEOUT_SECONDS": "7",
    "JWT_SECRET_KEY": "test-jwt-secret",
}


class EmailServiceTests(unittest.TestCase):
    def tearDown(self):
        get_settings.cache_clear()

    def test_smtp_integration_uses_gmail_starttls_login_and_timeout(self):
        with patch.dict(os.environ, SMTP_ENV):
            get_settings.cache_clear()
            server = MagicMock()
            smtp_factory = MagicMock(return_value=server)
            server.__enter__.return_value = server
            with patch("app.services.email_service.smtplib.SMTP", smtp_factory):
                EmailService().send_password_reset_email(
                    recipient="student@example.com",
                    reset_link="https://example.com/reset-password?token=abc",
                    reset_code="abc",
                )

        smtp_factory.assert_called_once()
        _, kwargs = smtp_factory.call_args
        self.assertEqual(kwargs["timeout"], 7.0)
        server.starttls.assert_called_once()
        server.login.assert_called_once_with("learner@example.com", "gmail-app-password-for-tests")
        server.send_message.assert_called_once()
        message = server.send_message.call_args.args[0]
        self.assertEqual(message["From"], "learner@example.com")
        self.assertEqual(message["To"], "student@example.com")
        self.assertIn("Reset your Chazy password", message["Subject"])
        self.assertIn("text/html", str(message))
        self.assertIn("support@example.com", str(message))

    def test_startup_validation_reports_missing_smtp_configuration(self):
        with patch.dict(os.environ, {"JWT_SECRET_KEY": "test-jwt-secret"}, clear=True):
            get_settings.cache_clear()
            self.assertFalse(validate_smtp_startup_configuration())
            health = EmailService().health_check()
            self.assertFalse(health["configured"])
            self.assertIn("SMTP_HOST", health["missing"])
            self.assertIn("SMTP_PASSWORD", health["missing"])

    def test_startup_validation_reports_invalid_gmail_smtp_values(self):
        env = dict(SMTP_ENV)
        env["SMTP_USE_TLS"] = "false"
        with patch.dict(os.environ, env):
            get_settings.cache_clear()
            self.assertFalse(validate_smtp_startup_configuration())
            health = EmailService().health_check()
            self.assertFalse(health["configured"])
            self.assertTrue(any("SMTP_USE_TLS" in issue for issue in health["issues"]))


class PasswordResetEmailFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.env_patch = patch.dict(os.environ, SMTP_ENV)
        self.env_patch.start()
        get_settings.cache_clear()

        self.engine = create_engine(
            f"sqlite:///{os.path.join(self.temp_dir.name, 'email-flow.db')}",
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
        self.env_patch.stop()
        get_settings.cache_clear()
        self.temp_dir.cleanup()

    @patch("app.services.auth_service.EmailService.send_password_reset_email")
    def test_forgot_password_generates_expiring_token_and_returns_generic_success(self, send_reset):
        self._sign_up("reset@example.com")
        response = self.client.post("/api/v1/auth/forgot-password", json={"email": "reset@example.com"})

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["message"], "If this email exists, password reset instructions have been sent.")
        send_reset.assert_called_once()
        _, kwargs = send_reset.call_args
        self.assertEqual(kwargs["recipient"], "reset@example.com")
        self.assertIn("token=", kwargs["reset_link"])
        self.assertGreaterEqual(len(kwargs["reset_code"]), 32)

        with self.SessionLocal() as db:
            user = db.scalar(select(User).where(User.email == "reset@example.com"))
            self.assertIsNotNone(user.password_reset_token_hash)
            self.assertIsNotNone(user.password_reset_expires_at)
            expires_at = user.password_reset_expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            self.assertGreater(expires_at, expires_at.now(timezone.utc))

        unknown = self.client.post("/api/v1/auth/forgot-password", json={"email": "unknown@example.com"})
        self.assertEqual(unknown.status_code, 200)

    @patch("app.services.auth_service.EmailService.send_password_reset_success_email")
    @patch("app.services.auth_service.EmailService.send_password_reset_email")
    def test_reset_password_validates_token_hashes_password_and_invalidates_token(self, send_reset, send_success):
        self._sign_up("reset-success@example.com")
        forgot = self.client.post("/api/v1/auth/forgot-password", json={"email": "reset-success@example.com"})
        self.assertEqual(forgot.status_code, 200, forgot.text)
        reset_token = send_reset.call_args.kwargs["reset_code"]

        response = self.client.post(
            "/api/v1/auth/reset-password",
            json={"token": reset_token, "new_password": "new-secret123"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        send_success.assert_called_once_with(recipient="reset-success@example.com")

        with self.SessionLocal() as db:
            user = db.scalar(select(User).where(User.email == "reset-success@example.com"))
            self.assertIsNone(user.password_reset_token_hash)
            self.assertIsNone(user.password_reset_expires_at)
            self.assertTrue(AuthService._verify_password("new-secret123", user.password_hash))
            self.assertFalse(AuthService._verify_password("secret123", user.password_hash))

        reuse = self.client.post(
            "/api/v1/auth/reset-password",
            json={"token": reset_token, "new_password": "another-secret123"},
        )
        self.assertEqual(reuse.status_code, 400)

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


if __name__ == "__main__":
    unittest.main()
