from __future__ import annotations

import base64
import hashlib
import hmac
import os

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.user import SignInRequest, SignUpRequest


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db

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
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")
        return user

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
