from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.achievement import AchievementEvaluateRequest, AchievementSummaryResponse
from app.services.achievement_service import AchievementService

router = APIRouter(prefix="/achievements", tags=["achievements"])


@router.get("/", response_model=AchievementSummaryResponse)
async def get_achievements(
    session_id: str = Query(..., min_length=1),
    user_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> AchievementSummaryResponse:
    return AchievementService(db).evaluate(session_id=session_id, user_id=user_id)


@router.post("/evaluate", response_model=AchievementSummaryResponse)
async def evaluate_achievements(
    payload: AchievementEvaluateRequest,
    db: Session = Depends(get_db),
) -> AchievementSummaryResponse:
    return AchievementService(db).evaluate(session_id=payload.session_id, user_id=payload.user_id)
