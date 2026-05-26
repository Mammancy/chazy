from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.services.token_service import TokenError, TokenPair, TokenService


class RefreshTokenReuseError(TokenError):
    pass


class RefreshTokenService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def issue_pair(self, user: User) -> TokenPair:
        tokens = TokenService.issue_pair(user)
        self._store_refresh_token(user=user, refresh_token=tokens.refresh_token)
        self.db.commit()
        return tokens

    def rotate(self, refresh_token: str) -> TokenPair:
        claims = TokenService.decode_refresh_claims(refresh_token)
        user_id = int(claims["sub"])
        token_record = self._find_refresh_token(refresh_token)
        if token_record is None or token_record.user_id != user_id:
            raise TokenError("Refresh token is not recognized.")

        now = self._now()
        if token_record.revoked_at is not None:
            token_record.reuse_detected_at = token_record.reuse_detected_at or now
            self.revoke_all_for_user(user_id, commit=False)
            self.db.add(token_record)
            self.db.commit()
            raise RefreshTokenReuseError("Refresh token reuse detected.")
        if self._as_aware(token_record.expires_at) <= now:
            token_record.revoked_at = now
            self.db.add(token_record)
            self.db.commit()
            raise TokenError("Refresh token expired.")

        user = self.db.get(User, user_id)
        if user is None or not user.is_active:
            raise TokenError("Refresh token user not found.")

        token_record.revoked_at = now
        self.db.add(token_record)

        tokens = TokenService.issue_pair(user)
        replacement = self._store_refresh_token(user=user, refresh_token=tokens.refresh_token)
        self.db.flush()
        token_record.replaced_by_token_id = replacement.id
        self.db.add(token_record)
        self.db.commit()
        return tokens

    def revoke_all_for_user(self, user_id: int, *, commit: bool = True) -> None:
        now = self._now()
        active_tokens = self.db.scalars(
            select(RefreshToken).where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
            )
        ).all()
        for token in active_tokens:
            token.revoked_at = now
            self.db.add(token)
        if commit:
            self.db.commit()

    def _store_refresh_token(self, *, user: User, refresh_token: str) -> RefreshToken:
        claims = TokenService.decode_refresh_claims(refresh_token)
        token_record = RefreshToken(
            user_id=user.id,
            token_hash=self._hash_token(refresh_token),
            token_jti=str(claims["jti"]),
            expires_at=datetime.fromtimestamp(int(claims["exp"]), tz=timezone.utc),
        )
        self.db.add(token_record)
        return token_record

    def _find_refresh_token(self, refresh_token: str) -> RefreshToken | None:
        return self.db.scalar(
            select(RefreshToken)
            .where(RefreshToken.token_hash == self._hash_token(refresh_token))
            .limit(1)
        )

    @staticmethod
    def _hash_token(refresh_token: str) -> str:
        return hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _as_aware(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
