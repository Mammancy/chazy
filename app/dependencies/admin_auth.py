from __future__ import annotations

import secrets

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.auth import bearer_scheme
from app.models.user import User
from app.services.token_service import TokenError, TokenService

ADMIN_ACCESS_COOKIE = "chazy_admin_access"
ADMIN_CSRF_COOKIE = "chazy_admin_csrf"
ADMIN_CSRF_HEADER = "X-CSRF-Token"


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def get_admin_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    admin_access_token: str | None = Cookie(default=None, alias=ADMIN_ACCESS_COOKIE),
    db: Session = Depends(get_db),
) -> User:
    token = credentials.credentials if credentials is not None and credentials.scheme.lower() == "bearer" else admin_access_token
    if not token:
        raise _unauthenticated()
    try:
        user_id = TokenService.decode_access_token(token)
    except TokenError as exc:
        raise _unauthenticated() from exc

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthenticated()
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")
    return user


def require_admin_csrf(
    request: Request,
    csrf_cookie: str | None = Cookie(default=None, alias=ADMIN_CSRF_COOKIE),
    csrf_header: str | None = Header(default=None, alias=ADMIN_CSRF_HEADER),
) -> None:
    if request.method.upper() in {"GET", "HEAD", "OPTIONS"}:
        return
    if not csrf_cookie or not csrf_header or not secrets.compare_digest(csrf_cookie, csrf_header):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid admin CSRF token.")


def _unauthenticated() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Admin authentication required.",
        headers={"WWW-Authenticate": "Bearer"},
    )
