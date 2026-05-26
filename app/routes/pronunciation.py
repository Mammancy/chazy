from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.auth import authenticated_session_id, get_current_user
from app.models.user import User
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PronunciationExerciseResponse]:
    return PronunciationService(db).list_exercises(difficulty=difficulty, limit=limit)


@router.post("/sessions", response_model=PronunciationSessionResponse)
async def create_pronunciation_session(
    payload: PronunciationSessionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PronunciationSessionResponse:
    try:
        secure_payload = payload.model_copy(
            update={"session_id": authenticated_session_id(current_user), "user_id": current_user.id}
        )
        return PronunciationService(db).create_session(secure_payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/sessions/{practice_session_id}/attempts", response_model=PronunciationAttemptResponse)
async def record_pronunciation_attempt(
    practice_session_id: int,
    payload: PronunciationAttemptCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PronunciationAttemptResponse:
    try:
        return PronunciationService(db).record_attempt(practice_session_id, payload, user_id=current_user.id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/progress", response_model=PronunciationProgressResponse)
async def get_pronunciation_progress(
    session_id: str = Query(..., min_length=1),
    user_id: int | None = Query(default=None, ge=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PronunciationProgressResponse:
    return PronunciationService(db).get_progress(
        session_id=authenticated_session_id(current_user),
        user_id=current_user.id,
    )
