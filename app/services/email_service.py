from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from html import escape

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


class EmailConfigurationError(RuntimeError):
    pass


class EmailDeliveryError(RuntimeError):
    pass


class EmailService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def health_check(self) -> dict:
        missing = self.missing_configuration()
        issues = self.configuration_issues()
        return {
            "configured": not missing and not issues,
            "missing": missing,
            "issues": issues,
            "host": self.settings.smtp_host or "",
            "port": self.settings.smtp_port,
            "tls_enabled": self.settings.smtp_use_tls,
            "ssl_enabled": self.settings.smtp_use_ssl,
            "from_email_configured": bool(self.settings.smtp_from_email),
            "username_configured": bool(self.settings.smtp_username),
            "timeout_seconds": self.settings.smtp_timeout_seconds,
        }

    def missing_configuration(self) -> list[str]:
        missing = []
        required = {
            "SMTP_HOST": self.settings.smtp_host,
            "SMTP_USERNAME": self.settings.smtp_username,
            "SMTP_PASSWORD": self.settings.smtp_password,
            "SMTP_FROM_EMAIL": self.settings.smtp_from_email,
        }
        for name, value in required.items():
            if not value or not str(value).strip():
                missing.append(name)
        if not self.settings.smtp_port:
            missing.append("SMTP_PORT")
        return missing

    def configuration_issues(self) -> list[str]:
        issues = []
        if self.settings.smtp_host and self.settings.smtp_host != "smtp.gmail.com":
            issues.append("SMTP_HOST must be smtp.gmail.com for Gmail App Password delivery.")
        if self.settings.smtp_port and self.settings.smtp_port != 587:
            issues.append("SMTP_PORT must be 587 for Gmail STARTTLS delivery.")
        if not self.settings.smtp_use_tls:
            issues.append("SMTP_USE_TLS must be true for Gmail STARTTLS delivery.")
        if self.settings.smtp_use_ssl:
            issues.append("SMTP_USE_SSL must be false for Gmail STARTTLS delivery.")
        return issues

    def send_password_reset_email(self, *, recipient: str, reset_link: str, reset_code: str) -> None:
        plain_text = (
            "Hello,\n\n"
            "We received a request to reset your Chazy password.\n\n"
            f"Reset link: {reset_link}\n\n"
            f"Reset code: {reset_code}\n\n"
            "If you did not request this, you can ignore this email.\n\n"
            "Need help? Contact support@example.com.\n\n"
            "Chazy"
        )
        html = self._password_reset_html(reset_link=reset_link, reset_code=reset_code)
        self._send_message(recipient=recipient, subject="Reset your Chazy password", plain_text=plain_text, html=html)

    def send_password_reset_success_email(self, *, recipient: str) -> None:
        plain_text = (
            "Hello,\n\n"
            "Your Chazy password was reset successfully.\n\n"
            "If you did not make this change, contact support@example.com immediately.\n\n"
            "Chazy"
        )
        html = self._password_reset_success_html()
        self._send_message(recipient=recipient, subject="Your Chazy password was reset", plain_text=plain_text, html=html)

    def _send_message(self, *, recipient: str, subject: str, plain_text: str, html: str) -> None:
        self._validate_config()
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.settings.smtp_from_email
        message["To"] = recipient
        message.set_content(plain_text)
        message.add_alternative(html, subtype="html")

        try:
            if self.settings.smtp_use_ssl:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(self.settings.smtp_host, self.settings.smtp_port, timeout=self._timeout(), context=context) as server:
                    self._login_if_needed(server)
                    server.send_message(message)
                return

            with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=self._timeout()) as server:
                if self.settings.smtp_use_tls:
                    server.starttls(context=ssl.create_default_context())
                self._login_if_needed(server)
                server.send_message(message)
        except (smtplib.SMTPException, OSError, TimeoutError) as exc:
            logger.exception(
                "SMTP email delivery failed host=%s port=%s tls=%s ssl=%s recipient_domain=%s error=%s",
                self.settings.smtp_host,
                self.settings.smtp_port,
                self.settings.smtp_use_tls,
                self.settings.smtp_use_ssl,
                self._recipient_domain(recipient),
                type(exc).__name__,
            )
            raise EmailDeliveryError("Failed to send email through SMTP.") from exc

    def _timeout(self) -> float:
        return max(5.0, float(self.settings.smtp_timeout_seconds or 20.0))

    def _validate_config(self) -> None:
        missing = self.missing_configuration()
        if missing:
            raise EmailConfigurationError("Missing SMTP configuration: " + ", ".join(missing))
        issues = self.configuration_issues()
        if issues:
            raise EmailConfigurationError("Invalid SMTP configuration: " + " ".join(issues))

    def _login_if_needed(self, server: smtplib.SMTP) -> None:
        if self.settings.smtp_username and self.settings.smtp_password:
            server.login(self.settings.smtp_username, self.settings.smtp_password)

    @staticmethod
    def _recipient_domain(recipient: str) -> str:
        return recipient.split("@", 1)[1].lower() if "@" in recipient else "unknown"

    @staticmethod
    def _password_reset_html(*, reset_link: str, reset_code: str) -> str:
        safe_link = escape(reset_link, quote=True)
        safe_code = escape(reset_code)
        return f"""<!doctype html>
<html>
  <body style="margin:0;background:#f6f8fb;font-family:Arial,sans-serif;color:#172033;">
    <div style="max-width:620px;margin:0 auto;padding:32px 18px;">
      <div style="background:#ffffff;border-radius:12px;padding:28px;border:1px solid #e5e9f0;">
        <h1 style="margin:0 0 12px;font-size:24px;color:#1f6feb;">Chazy</h1>
        <h2 style="margin:0 0 16px;font-size:20px;">Reset your password</h2>
        <p style="line-height:1.6;">We received a request to reset your Chazy password. Use the secure link below or enter the reset token in the app.</p>
        <p style="margin:24px 0;"><a href="{safe_link}" style="background:#1f6feb;color:#ffffff;padding:12px 18px;border-radius:8px;text-decoration:none;font-weight:bold;">Reset password</a></p>
        <p style="line-height:1.6;"><strong>Reset token:</strong></p>
        <p style="font-family:Consolas,monospace;background:#eef3fb;padding:12px;border-radius:8px;word-break:break-all;">{safe_code}</p>
        <p style="line-height:1.6;color:#5c667a;">This link expires in 30 minutes. If you did not request this, you can ignore this email.</p>
        <p style="line-height:1.6;color:#5c667a;">Need help? Contact support@example.com.</p>
      </div>
    </div>
  </body>
</html>"""

    @staticmethod
    def _password_reset_success_html() -> str:
        return """<!doctype html>
<html>
  <body style="margin:0;background:#f6f8fb;font-family:Arial,sans-serif;color:#172033;">
    <div style="max-width:620px;margin:0 auto;padding:32px 18px;">
      <div style="background:#ffffff;border-radius:12px;padding:28px;border:1px solid #e5e9f0;">
        <h1 style="margin:0 0 12px;font-size:24px;color:#1f6feb;">Chazy</h1>
        <h2 style="margin:0 0 16px;font-size:20px;">Password reset successful</h2>
        <p style="line-height:1.6;">Your Chazy password was reset successfully.</p>
        <p style="line-height:1.6;color:#5c667a;">If you did not make this change, contact support@example.com immediately.</p>
      </div>
    </div>
  </body>
</html>"""
