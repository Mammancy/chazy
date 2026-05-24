from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

from app.config.settings import get_settings
from app.models.user import User


class TokenError(ValueError):
    pass


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int


class TokenService:
    algorithm = "HS256"

    @classmethod
    def issue_pair(cls, user: User) -> TokenPair:
        settings = get_settings()
        access_ttl = settings.jwt_access_token_minutes * 60
        refresh_ttl = settings.jwt_refresh_token_days * 24 * 60 * 60
        return TokenPair(
            access_token=cls._encode(user=user, token_type="access", ttl_seconds=access_ttl),
            refresh_token=cls._encode(user=user, token_type="refresh", ttl_seconds=refresh_ttl),
            token_type="bearer",
            expires_in=access_ttl,
        )

    @classmethod
    def decode_access_token(cls, token: str) -> int:
        return int(cls._decode_payload(token, expected_type="access")["sub"])

    @classmethod
    def decode_access_claims(cls, token: str) -> dict[str, Any]:
        return cls._decode_payload(token, expected_type="access")

    @classmethod
    def decode_refresh_token(cls, token: str) -> int:
        return int(cls._decode_payload(token, expected_type="refresh")["sub"])

    @classmethod
    def _encode(cls, *, user: User, token_type: str, ttl_seconds: int) -> str:
        settings = get_settings()
        now = int(time.time())
        header = {"alg": cls.algorithm, "typ": "JWT"}
        payload = {
            "iss": settings.jwt_issuer,
            "sub": str(user.id),
            "typ": token_type,
            "iat": now,
            "exp": now + ttl_seconds,
            "email": user.email,
            "role": user.role,
        }
        signing_input = f"{cls._b64_json(header)}.{cls._b64_json(payload)}"
        signature = cls._sign(signing_input)
        return f"{signing_input}.{signature}"

    @classmethod
    def _decode_payload(cls, token: str, *, expected_type: str) -> dict[str, Any]:
        settings = get_settings()
        try:
            header_raw, payload_raw, signature = token.split(".", 2)
        except ValueError as exc:
            raise TokenError("Malformed token.") from exc

        signing_input = f"{header_raw}.{payload_raw}"
        if not hmac.compare_digest(cls._sign(signing_input), signature):
            raise TokenError("Invalid token signature.")

        header = cls._b64_decode_json(header_raw)
        payload = cls._b64_decode_json(payload_raw)
        if header.get("alg") != cls.algorithm:
            raise TokenError("Unsupported token algorithm.")
        if payload.get("iss") != settings.jwt_issuer:
            raise TokenError("Invalid token issuer.")
        if payload.get("typ") != expected_type:
            raise TokenError("Invalid token type.")
        if int(payload.get("exp", 0)) < int(time.time()):
            raise TokenError("Token expired.")

        try:
            int(payload["sub"])
        except (KeyError, TypeError, ValueError) as exc:
            raise TokenError("Invalid token subject.") from exc
        return payload

    @classmethod
    def _sign(cls, signing_input: str) -> str:
        secret = get_settings().jwt_secret_key.encode("utf-8")
        digest = hmac.new(secret, signing_input.encode("ascii"), hashlib.sha256).digest()
        return cls._b64_bytes(digest)

    @staticmethod
    def _b64_json(value: dict[str, Any]) -> str:
        return TokenService._b64_bytes(json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8"))

    @staticmethod
    def _b64_decode_json(value: str) -> dict[str, Any]:
        padded = value + "=" * (-len(value) % 4)
        try:
            decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
            return json.loads(decoded.decode("utf-8"))
        except (ValueError, json.JSONDecodeError) as exc:
            raise TokenError("Invalid token payload.") from exc

    @staticmethod
    def _b64_bytes(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")
