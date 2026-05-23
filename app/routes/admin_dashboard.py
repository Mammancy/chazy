from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, select_autoescape

template_dir = Path(__file__).resolve().parents[1] / "templates"
template_env = Environment(
    loader=FileSystemLoader(str(template_dir)),
    autoescape=select_autoescape(["html", "xml"]),
    cache_size=0,
)
templates = Jinja2Templates(env=template_env)

router = APIRouter(tags=["admin-dashboard"])


@router.get("/admin", include_in_schema=False)
async def admin_home() -> RedirectResponse:
    return RedirectResponse(url="/admin/dashboard")


@router.get("/admin/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def admin_dashboard(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "admin/dashboard.html",
        {
            "app_name": "Chazy",
            "analytics_endpoint": "/api/v1/admin/analytics/dashboard",
        },
    )


@router.get("/admin/users", response_class=HTMLResponse, include_in_schema=False)
async def admin_user_analytics(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "admin/users.html",
        {
            "app_name": "Chazy",
            "analytics_endpoint": "/api/v1/admin/analytics/dashboard",
        },
    )


@router.get("/admin/learning", response_class=HTMLResponse, include_in_schema=False)
async def admin_learning_analytics(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "admin/learning.html",
        {
            "app_name": "Chazy",
            "analytics_endpoint": "/api/v1/admin/analytics/dashboard",
        },
    )
