from pathlib import Path
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session

from app.config.settings import get_settings
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
    cache_size=100,
)
templates = Jinja2Templates(env=template_env)

router = APIRouter(tags=["admin-dashboard"])


@router.get("/admin", include_in_schema=False)
def admin_home(current_admin: User = Depends(get_admin_user)) -> RedirectResponse:
    return RedirectResponse(url="/admin/dashboard")


@router.get("/admin/login", response_class=HTMLResponse, include_in_schema=False, response_model=None)
def admin_login_form(request: Request, db: Session = Depends(get_db)) -> HTMLResponse | RedirectResponse:
    if not AuthService(db).admin_exists():
        return RedirectResponse(url="/admin/setup", status_code=status.HTTP_303_SEE_OTHER)
    return _login_response(request)


@router.get("/admin/setup", response_class=HTMLResponse, include_in_schema=False, response_model=None)
def admin_setup_form(request: Request, db: Session = Depends(get_db)) -> HTMLResponse | RedirectResponse:
    if AuthService(db).admin_exists():
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request,
        "admin/setup.html",
        {"app_name": "Confidence", "error": None},
    )


@router.post("/admin/setup", include_in_schema=False, response_model=None)
async def admin_setup(request: Request, db: Session = Depends(get_db)) -> RedirectResponse | HTMLResponse:
    auth_service = AuthService(db)
    if auth_service.admin_exists():
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)

    body = (await request.body()).decode("utf-8")
    fields = parse_qs(body)
    try:
        user = auth_service.create_first_admin(_signup_from_fields(fields))
    except HTTPException as exc:
        AdminAuditService(db).log(admin_user=None, action="admin_setup_failed", request=request, detail=str(exc.detail))
        return templates.TemplateResponse(
            request,
            "admin/setup.html",
            {"app_name": "Confidence", "error": str(exc.detail)},
            status_code=exc.status_code,
        )

    tokens = TokenService.issue_pair(user)
    csrf_token = new_csrf_token()
    response = RedirectResponse(url="/admin/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    _set_admin_cookies(request, response, access_token=tokens.access_token, csrf_token=csrf_token, max_age=tokens.expires_in)
    AdminAuditService(db).log(admin_user=user, action="admin_setup_completed", request=request)
    return response


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
    _set_admin_cookies(request, response, access_token=tokens.access_token, csrf_token=csrf_token, max_age=tokens.expires_in)
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
    secure = _admin_cookie_secure(request)
    response.delete_cookie(ADMIN_ACCESS_COOKIE, secure=secure, samesite="lax")
    response.delete_cookie(ADMIN_CSRF_COOKIE, secure=secure, samesite="lax")
    return response


@router.get("/admin/dashboard", response_class=HTMLResponse, include_in_schema=False)
def admin_dashboard(request: Request, current_admin: User = Depends(get_admin_user)) -> HTMLResponse:
    return _admin_template(
        request,
        "admin/dashboard.html",
        current_admin,
        analytics_endpoint="/api/v1/admin/analytics/dashboard",
    )


@router.get("/admin/users", response_class=HTMLResponse, include_in_schema=False)
def admin_user_analytics(request: Request, current_admin: User = Depends(get_admin_user)) -> HTMLResponse:
    return _admin_template(
        request,
        "admin/users.html",
        current_admin,
        analytics_endpoint="/api/v1/admin/analytics/dashboard",
    )


@router.get("/admin/learning", response_class=HTMLResponse, include_in_schema=False)
def admin_learning_analytics(request: Request, current_admin: User = Depends(get_admin_user)) -> HTMLResponse:
    return _admin_template(
        request,
        "admin/learning.html",
        current_admin,
        analytics_endpoint="/api/v1/admin/analytics/dashboard",
    )


@router.get("/admin/conversations", response_class=HTMLResponse, include_in_schema=False)
def admin_conversation_analytics(request: Request, current_admin: User = Depends(get_admin_user)) -> HTMLResponse:
    return _admin_template(
        request,
        "admin/conversations.html",
        current_admin,
        analytics_endpoint="/api/v1/admin/analytics/dashboard",
    )


@router.get("/admin/openai-usage", response_class=HTMLResponse, include_in_schema=False)
def admin_openai_usage(request: Request, current_admin: User = Depends(get_admin_user)) -> HTMLResponse:
    return _admin_template(
        request,
        "admin/openai_usage.html",
        current_admin,
        analytics_endpoint="/api/v1/admin/analytics/dashboard",
    )


@router.get("/admin/user-management", response_class=HTMLResponse, include_in_schema=False)
def admin_user_management(request: Request, current_admin: User = Depends(get_admin_user)) -> HTMLResponse:
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
            "app_name": "Confidence",
            "admin_user": current_admin,
            "csrf_token": csrf_token,
            **context,
        },
    )


def _login_response(request: Request, error: str | None = None, status_code: int = 200) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "admin/login.html",
        {"app_name": "Confidence", "error": error},
        status_code=status_code,
    )


def _set_admin_cookies(
    request: Request,
    response: RedirectResponse,
    *,
    access_token: str,
    csrf_token: str,
    max_age: int,
) -> None:
    secure = _admin_cookie_secure(request)
    response.set_cookie(
        ADMIN_ACCESS_COOKIE,
        access_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=max_age,
    )
    response.set_cookie(
        ADMIN_CSRF_COOKIE,
        csrf_token,
        httponly=False,
        secure=secure,
        samesite="lax",
        max_age=max_age,
    )


def _admin_cookie_secure(request: Request) -> bool:
    settings = get_settings()
    environment = settings.environment.strip().lower()
    if environment in {"production", "prod"}:
        return True
    if request.url.scheme == "https":
        return True
    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    if forwarded_proto.split(",", 1)[0].strip().lower() == "https":
        return True
    forwarded = request.headers.get("forwarded", "").lower()
    return "proto=https" in forwarded


def _signup_from_fields(fields: dict[str, list[str]]):
    from app.schemas.user import SignUpRequest

    return SignUpRequest(
        full_name=(fields.get("full_name") or [""])[0],
        email=(fields.get("email") or [""])[0],
        phone_number=(fields.get("phone_number") or [""])[0],
        country=(fields.get("country") or [""])[0],
        state=(fields.get("state") or [""])[0],
        password=(fields.get("password") or [""])[0],
    )
