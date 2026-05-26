from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response

from app.services.token_service import TokenError, TokenService


class AdminAuthorizationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if not self._is_admin_path(path) or path in {"/admin/login", "/admin/setup"}:
            return await call_next(request)

        error_status = self._authorize_request(request)
        if error_status != 200:
            if path.startswith("/api/"):
                return JSONResponse({"detail": "Admin authentication required."}, status_code=error_status)
            return RedirectResponse(url="/admin/login", status_code=303)

        return await call_next(request)

    @staticmethod
    def _is_admin_path(path: str) -> bool:
        return path == "/admin" or path.startswith("/admin/") or path.startswith("/api/v1/admin/")

    @staticmethod
    def _authorize_request(request: Request) -> int:
        auth_header = request.headers.get("authorization", "")
        token = ""
        if auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1].strip()
        if not token:
            token = request.cookies.get("chazy_admin_access", "")
        if not token:
            return 401

        try:
            claims = TokenService.decode_access_claims(token)
        except TokenError:
            return 401
        if claims.get("role") != "admin":
            return 403
        return 200
