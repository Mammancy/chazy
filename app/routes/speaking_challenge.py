from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
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
    db: Session = Depends(get_db),
) -> DailySpeakingChallengesResponse:
    return SpeakingChallengeService(db).get_daily_challenges(
        session_id=session_id,
        user_id=user_id,
        challenge_date=challenge_date,
    )


@router.post("/{challenge_id}/complete", response_model=SpeakingChallengeCompletionResponse)
async def complete_speaking_challenge(
    challenge_id: int,
    payload: SpeakingChallengeCompletionCreate,
    challenge_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> SpeakingChallengeCompletionResponse:
    try:
        return SpeakingChallengeService(db).complete_challenge(
            challenge_id=challenge_id,
            payload=payload,
            challenge_date=challenge_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/streak", response_model=SpeakingChallengeStreakResponse)
async def get_speaking_challenge_streak(
    session_id: str = Query(..., min_length=1),
    user_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> SpeakingChallengeStreakResponse:
    return SpeakingChallengeService(db).get_streak(session_id=session_id, user_id=user_id)
