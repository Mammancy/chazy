from pathlib import Path
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.admin_auth import ADMIN_ACCESS_COOKIE, ADMIN_CSRF_COOKIE, get_admin_user, new_csrf_token
from app.models.user import User
from app.schemas.user import SignInRequest
from app.services.admin_audit_service import AdminAuditService
from app.services.auth_service import AuthService
from app.services.token_service import TokenService

template_dir = Path(__file__).resolve().parents[1] / "templates"
template_env = Environment(
    loader=FileSystemLoader(str(template_dir)),
    autoescape=select_autoescape(["html", "xml"]),
    cache_size=0,
)
templates = Jinja2Templates(env=template_env)

router = APIRouter(tags=["admin-dashboard"])


@router.get("/admin", include_in_schema=False)
async def admin_home(current_admin: User = Depends(get_admin_user)) -> RedirectResponse:
    return RedirectResponse(url="/admin/dashboard")


@router.get("/admin/login", response_class=HTMLResponse, include_in_schema=False)
async def admin_login_form(request: Request) -> HTMLResponse:
    return _login_response(request)


@router.post("/admin/login", include_in_schema=False, response_model=None)
async def admin_login(request: Request, db: Session = Depends(get_db)) -> RedirectResponse | HTMLResponse:
    body = (await request.body()).decode("utf-8")
    fields = parse_qs(body)
    email = (fields.get("email") or [""])[0]
    password = (fields.get("password") or [""])[0]

    try:
        user = AuthService(db).sign_in(SignInRequest(email=email, password=password))
    except HTTPException as exc:
        AdminAuditService(db).log(admin_user=None, action="admin_login_failed", request=request, detail=email)
        return _login_response(request, error="Invalid admin email or password.", status_code=exc.status_code)

    if user.role != "admin":
        AdminAuditService(db).log(
            admin_user=user,
            action="admin_login_forbidden",
            request=request,
            detail="Non-admin attempted to access the admin dashboard.",
        )
        return _login_response(request, error="Admin access required.", status_code=status.HTTP_403_FORBIDDEN)

    tokens = TokenService.issue_pair(user)
    csrf_token = new_csrf_token()
    response = RedirectResponse(url="/admin/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(ADMIN_ACCESS_COOKIE, tokens.access_token, httponly=True, secure=False, samesite="lax", max_age=tokens.expires_in)
    response.set_cookie(ADMIN_CSRF_COOKIE, csrf_token, httponly=False, secure=False, samesite="lax", max_age=tokens.expires_in)
    AdminAuditService(db).log(admin_user=user, action="admin_login_success", request=request)
    return response


@router.post("/admin/logout", include_in_schema=False)
async def admin_logout(
    request: Request,
    current_admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    AdminAuditService(db).log(admin_user=current_admin, action="admin_logout", request=request)
    response = RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(ADMIN_ACCESS_COOKIE)
    response.delete_cookie(ADMIN_CSRF_COOKIE)
    return response


@router.get("/admin/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def admin_dashboard(request: Request, current_admin: User = Depends(get_admin_user)) -> HTMLResponse:
    return _admin_template(
        request,
        "admin/dashboard.html",
        current_admin,
        analytics_endpoint="/api/v1/admin/analytics/dashboard",
    )


@router.get("/admin/users", response_class=HTMLResponse, include_in_schema=False)
async def admin_user_analytics(request: Request, current_admin: User = Depends(get_admin_user)) -> HTMLResponse:
    return _admin_template(
        request,
        "admin/users.html",
        current_admin,
        analytics_endpoint="/api/v1/admin/analytics/dashboard",
    )


@router.get("/admin/learning", response_class=HTMLResponse, include_in_schema=False)
async def admin_learning_analytics(request: Request, current_admin: User = Depends(get_admin_user)) -> HTMLResponse:
    return _admin_template(
        request,
        "admin/learning.html",
        current_admin,
        analytics_endpoint="/api/v1/admin/analytics/dashboard",
    )


@router.get("/admin/conversations", response_class=HTMLResponse, include_in_schema=False)
async def admin_conversation_analytics(request: Request, current_admin: User = Depends(get_admin_user)) -> HTMLResponse:
    return _admin_template(
        request,
        "admin/conversations.html",
        current_admin,
        analytics_endpoint="/api/v1/admin/analytics/dashboard",
    )


@router.get("/admin/openai-usage", response_class=HTMLResponse, include_in_schema=False)
async def admin_openai_usage(request: Request, current_admin: User = Depends(get_admin_user)) -> HTMLResponse:
    return _admin_template(
        request,
        "admin/openai_usage.html",
        current_admin,
        analytics_endpoint="/api/v1/admin/analytics/dashboard",
    )


@router.get("/admin/user-management", response_class=HTMLResponse, include_in_schema=False)
async def admin_user_management(request: Request, current_admin: User = Depends(get_admin_user)) -> HTMLResponse:
    return _admin_template(
        request,
        "admin/user_management.html",
        current_admin,
        users_endpoint="/api/v1/admin/users",
    )


def _admin_template(request: Request, template_name: str, current_admin: User, **context) -> HTMLResponse:
    csrf_token = request.cookies.get(ADMIN_CSRF_COOKIE, "")
    return templates.TemplateResponse(
        request,
        template_name,
        {
            "app_name": "Chazy",
            "admin_user": current_admin,
            "csrf_token": csrf_token,
            **context,
        },
    )


def _login_response(request: Request, error: str | None = None, status_code: int = 200) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "admin/login.html",
        {"app_name": "Chazy", "error": error},
        status_code=status_code,
    )
