from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.auth import authenticated_session_id, get_current_user
from app.models.user import User
from app.schemas.achievement import AchievementEvaluateRequest, AchievementSummaryResponse
from app.services.achievement_service import AchievementService

router = APIRouter(prefix="/achievements", tags=["achievements"])


@router.get("/", response_model=AchievementSummaryResponse)
async def get_achievements(
    session_id: str = Query(..., min_length=1),
    user_id: int | None = Query(default=None, ge=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AchievementSummaryResponse:
    return AchievementService(db).evaluate(session_id=authenticated_session_id(current_user), user_id=current_user.id)


@router.post("/evaluate", response_model=AchievementSummaryResponse)
async def evaluate_achievements(
    payload: AchievementEvaluateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AchievementSummaryResponse:
    return AchievementService(db).evaluate(session_id=authenticated_session_id(current_user), user_id=current_user.id)
