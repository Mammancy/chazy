from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.admin_analytics import AdminAnalyticsDashboardResponse
from app.services.admin_analytics_service import AdminAnalyticsService

router = APIRouter(prefix="/admin/analytics", tags=["admin-analytics"])


@router.get("/dashboard", response_model=AdminAnalyticsDashboardResponse)
async def get_admin_analytics_dashboard(
    window_days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
) -> AdminAnalyticsDashboardResponse:
    return AdminAnalyticsService(db).get_dashboard(window_days=window_days)
