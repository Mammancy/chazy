from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.models.user import User
from app.schemas.user import ForgotPasswordRequest, ResetPasswordRequest, SignInRequest, SignUpRequest
from app.services.email_service import EmailConfigurationError, EmailService

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    def sign_up(self, payload: SignUpRequest) -> User:
        email = payload.email.lower().strip()
        existing = self.db.scalar(select(User).where(User.email == email).limit(1))
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists.",
            )

        user = User(
            external_id=f"email:{email}",
            email=email,
            full_name=payload.full_name.strip(),
            phone_number=payload.phone_number.strip(),
            country=payload.country.strip(),
            state=payload.state.strip(),
            password_hash=self._hash_password(payload.password),
            timezone="Africa/Lagos",
            is_active=True,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def sign_in(self, payload: SignInRequest) -> User:
        email = payload.email.lower().strip()
        user = self.db.scalar(select(User).where(User.email == email).limit(1))
        if user is None or not user.password_hash or not self._verify_password(payload.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This account is disabled.",
            )
        return user

    def get_profile(self, user_id: int) -> User:
        user = self.db.get(User, user_id)
        if user is None or not user.is_active:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")
        return user

    def update_response_length_preference(self, user_id: int, preference: str) -> User:
        user = self.get_profile(user_id)
        normalized = preference.upper()
        if normalized not in {"SHORT", "MEDIUM", "DETAILED"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid response length preference.")
        user.response_length_preference = normalized
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def delete_account(self, user_id: int) -> None:
        user = self.db.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")

        user.email = f"deleted-user-{user.id}@deleted.local"
        user.external_id = f"deleted:{user.id}"
        user.full_name = "Deleted user"
        user.phone_number = None
        user.country = None
        user.state = None
        user.password_hash = None
        user.password_reset_token_hash = None
        user.password_reset_expires_at = None
        user.is_active = False
        self.db.add(user)
        self.db.commit()

    def forgot_password(self, payload: ForgotPasswordRequest) -> None:
        email = payload.email.lower().strip()
        user = self.db.scalar(select(User).where(User.email == email).limit(1))
        if user is None:
            logger.info("password_reset requested for unknown email")
            return

        reset_token = secrets.token_urlsafe(32)
        user.password_reset_token_hash = self._hash_reset_token(reset_token)
        user.password_reset_expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
        self.db.add(user)
        self.db.commit()

        reset_link = self._build_reset_link(reset_token)
        try:
            EmailService().send_password_reset_email(
                recipient=email,
                reset_link=reset_link,
                reset_code=reset_token,
            )
        except EmailConfigurationError as exc:
            logger.exception("password_reset email configuration error user_id=%s", user.id)
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("password_reset email send failed user_id=%s", user.id)
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to send password reset email.") from exc

    def reset_password(self, payload: ResetPasswordRequest) -> None:
        token_hash = self._hash_reset_token(payload.token)
        user = self.db.scalar(select(User).where(User.password_reset_token_hash == token_hash).limit(1))
        if user is None or user.password_reset_expires_at is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token.")

        expires_at = user.password_reset_expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token.")

        user.password_hash = self._hash_password(payload.new_password)
        user.password_reset_token_hash = None
        user.password_reset_expires_at = None
        self.db.add(user)
        self.db.commit()

    def _build_reset_link(self, token: str) -> str:
        separator = "&" if "?" in self.settings.password_reset_base_url else "?"
        return f"{self.settings.password_reset_base_url}{separator}{urlencode({'token': token})}"

    @staticmethod
    def _hash_password(password: str) -> str:
        salt = os.urandom(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
        return "pbkdf2_sha256$120000$" + base64.b64encode(salt).decode("ascii") + "$" + base64.b64encode(digest).decode("ascii")

    @staticmethod
    def _verify_password(password: str, stored_hash: str) -> bool:
        try:
            algorithm, iterations_raw, salt_raw, digest_raw = stored_hash.split("$", 3)
            if algorithm != "pbkdf2_sha256":
                return False
            iterations = int(iterations_raw)
            salt = base64.b64decode(salt_raw.encode("ascii"))
            expected = base64.b64decode(digest_raw.encode("ascii"))
        except (ValueError, TypeError):
            return False

        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual, expected)

    @staticmethod
    def _hash_reset_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

