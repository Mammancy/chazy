from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.pronunciation import (
    PronunciationAttemptCreate,
    PronunciationAttemptResponse,
    PronunciationExerciseResponse,
    PronunciationProgressResponse,
    PronunciationSessionCreate,
    PronunciationSessionResponse,
)
from app.services.pronunciation_service import PronunciationService

router = APIRouter(prefix="/pronunciation", tags=["pronunciation"])


@router.get("/words", response_model=list[PronunciationExerciseResponse])
async def list_pronunciation_words(
    difficulty: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[PronunciationExerciseResponse]:
    return PronunciationService(db).list_exercises(difficulty=difficulty, limit=limit)


@router.post("/sessions", response_model=PronunciationSessionResponse)
async def create_pronunciation_session(
    payload: PronunciationSessionCreate,
    db: Session = Depends(get_db),
) -> PronunciationSessionResponse:
    try:
        return PronunciationService(db).create_session(payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/sessions/{practice_session_id}/attempts", response_model=PronunciationAttemptResponse)
async def record_pronunciation_attempt(
    practice_session_id: int,
    payload: PronunciationAttemptCreate,
    db: Session = Depends(get_db),
) -> PronunciationAttemptResponse:
    try:
        return PronunciationService(db).record_attempt(practice_session_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/progress", response_model=PronunciationProgressResponse)
async def get_pronunciation_progress(
    session_id: str = Query(..., min_length=1),
    user_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> PronunciationProgressResponse:
    return PronunciationService(db).get_progress(session_id=session_id, user_id=user_id)
