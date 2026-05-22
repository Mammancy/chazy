from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.learning_analytics import LearningAnalyticsResponse
from app.services.learning_analytics_service import LearningAnalyticsService

router = APIRouter(prefix="/learning-analytics", tags=["learning-analytics"])


@router.get("/", response_model=LearningAnalyticsResponse)
async def get_learning_analytics(
    session_id: str = Query(..., min_length=1),
    user_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> LearningAnalyticsResponse:
    return LearningAnalyticsService(db).get_analytics(session_id=session_id, user_id=user_id)
