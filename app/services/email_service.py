from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from app.config.settings import get_settings


class EmailConfigurationError(RuntimeError):
    pass


class EmailService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def send_password_reset_email(self, *, recipient: str, reset_link: str, reset_code: str) -> None:
        self._validate_config()
        message = EmailMessage()
        message["Subject"] = "Reset your Chazy password"
        message["From"] = self.settings.smtp_from_email
        message["To"] = recipient
        message.set_content(
            "Hello,\n\n"
            "We received a request to reset your Chazy password.\n\n"
            f"Reset link: {reset_link}\n\n"
            f"Reset code: {reset_code}\n\n"
            "If you did not request this, you can ignore this email.\n\n"
            "Chazy"
        )

        if self.settings.smtp_use_ssl:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(self.settings.smtp_host, self.settings.smtp_port, timeout=self.settings.smtp_timeout_seconds, context=context) as server:
                self._login_if_needed(server)
                server.send_message(message)
            return

        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=self.settings.smtp_timeout_seconds) as server:
            if self.settings.smtp_use_tls:
                server.starttls(context=ssl.create_default_context())
            self._login_if_needed(server)
            server.send_message(message)

    def _validate_config(self) -> None:
        missing = []
        if not self.settings.smtp_host:
            missing.append("SMTP_HOST")
        if not self.settings.smtp_from_email:
            missing.append("SMTP_FROM_EMAIL")
        if missing:
            raise EmailConfigurationError("Missing SMTP configuration: " + ", ".join(missing))

    def _login_if_needed(self, server: smtplib.SMTP) -> None:
        if self.settings.smtp_username and self.settings.smtp_password:
            server.login(self.settings.smtp_username, self.settings.smtp_password)
