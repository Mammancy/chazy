from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.auth import authenticated_session_id, get_current_user
from app.models.user import User
from app.schemas.speaking_challenge import (
    DailySpeakingChallengesResponse,
    SpeakingChallengeCompletionCreate,
    SpeakingChallengeCompletionResponse,
    SpeakingChallengeStreakResponse,
)
from app.services.speaking_challenge_service import SpeakingChallengeService

router = APIRouter(prefix="/speaking-challenges", tags=["speaking-challenges"])


@router.get("/daily", response_model=DailySpeakingChallengesResponse)
async def get_daily_speaking_challenges(
    session_id: str = Query(..., min_length=1),
    user_id: int | None = Query(default=None, ge=1),
    challenge_date: date | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DailySpeakingChallengesResponse:
    return SpeakingChallengeService(db).get_daily_challenges(
        session_id=authenticated_session_id(current_user),
        user_id=current_user.id,
        challenge_date=challenge_date,
    )


@router.post("/{challenge_id}/complete", response_model=SpeakingChallengeCompletionResponse)
async def complete_speaking_challenge(
    challenge_id: int,
    payload: SpeakingChallengeCompletionCreate,
    challenge_date: date | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SpeakingChallengeCompletionResponse:
    try:
        secure_payload = payload.model_copy(
            update={"session_id": authenticated_session_id(current_user), "user_id": current_user.id}
        )
        return SpeakingChallengeService(db).complete_challenge(
            challenge_id=challenge_id,
            payload=secure_payload,
            challenge_date=challenge_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/streak", response_model=SpeakingChallengeStreakResponse)
async def get_speaking_challenge_streak(
    session_id: str = Query(..., min_length=1),
    user_id: int | None = Query(default=None, ge=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SpeakingChallengeStreakResponse:
    return SpeakingChallengeService(db).get_streak(
        session_id=authenticated_session_id(current_user),
        user_id=current_user.id,
    )
