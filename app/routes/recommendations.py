from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.auth import authenticated_session_id, get_current_user
from app.models.user import User
from app.schemas.recommendation import PersonalizedRecommendationResponse
from app.services.recommendation_service import RecommendationService

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("/personalized", response_model=PersonalizedRecommendationResponse)
async def get_personalized_recommendations(
    session_id: str = Query(..., min_length=1),
    user_id: int | None = Query(default=None, ge=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PersonalizedRecommendationResponse:
    return RecommendationService(db).get_recommendations(
        session_id=authenticated_session_id(current_user),
        user_id=current_user.id,
    )
