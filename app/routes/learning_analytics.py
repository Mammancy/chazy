from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.auth import authenticated_session_id, get_current_user
from app.models.user import User
from app.schemas.learning_analytics import LearningAnalyticsResponse
from app.services.learning_analytics_service import LearningAnalyticsService

router = APIRouter(prefix="/learning-analytics", tags=["learning-analytics"])


@router.get("/", response_model=LearningAnalyticsResponse)
async def get_learning_analytics(
    session_id: str = Query(..., min_length=1),
    user_id: int | None = Query(default=None, ge=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LearningAnalyticsResponse:
    return LearningAnalyticsService(db).get_analytics(
        session_id=authenticated_session_id(current_user),
        user_id=current_user.id,
    )
