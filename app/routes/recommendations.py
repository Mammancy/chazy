from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.recommendation import PersonalizedRecommendationResponse
from app.services.recommendation_service import RecommendationService

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("/personalized", response_model=PersonalizedRecommendationResponse)
async def get_personalized_recommendations(
    session_id: str = Query(..., min_length=1),
    user_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> PersonalizedRecommendationResponse:
    return RecommendationService(db).get_recommendations(session_id=session_id, user_id=user_id)
