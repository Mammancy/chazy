from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.auth import authenticated_session_id, get_current_user
from app.models.user import User
from app.schemas.vocabulary_notebook import (
    VocabularyBookmarkFromConversationRequest,
    VocabularyEntryCreate,
    VocabularyEntryResponse,
    VocabularyEntryUpdate,
    VocabularyNotebookResponse,
    VocabularyNotebookStatsResponse,
    VocabularyReviewRequest,
    VocabularyReviewSessionCreate,
    VocabularyReviewSessionResponse,
    VocabularyReviewSessionSubmit,
)
from app.services.vocabulary_notebook_service import VocabularyNotebookService

router = APIRouter(prefix="/vocabulary-notebook", tags=["vocabulary-notebook"])


@router.get("/", response_model=VocabularyNotebookResponse)
async def list_vocabulary_entries(
    session_id: str = Query(..., min_length=1),
    user_id: int | None = Query(default=None, ge=1),
    mastery_status: str | None = Query(default=None),
    bookmarked: bool | None = Query(default=None),
    due_only: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VocabularyNotebookResponse:
    return VocabularyNotebookService(db).list_entries(
        session_id=authenticated_session_id(current_user),
        user_id=current_user.id,
        mastery_status=mastery_status,
        bookmarked=bookmarked,
        due_only=due_only,
    )


@router.post("/", response_model=VocabularyEntryResponse)
async def create_vocabulary_entry(
    payload: VocabularyEntryCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VocabularyEntryResponse:
    secure_payload = payload.model_copy(
        update={"session_id": authenticated_session_id(current_user), "user_id": current_user.id}
    )
    return VocabularyNotebookService(db).create_entry(secure_payload)


@router.post("/bookmark-from-conversation", response_model=VocabularyEntryResponse)
async def bookmark_word_from_conversation(
    payload: VocabularyBookmarkFromConversationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VocabularyEntryResponse:
    try:
        secure_payload = payload.model_copy(
            update={"session_id": authenticated_session_id(current_user), "user_id": current_user.id}
        )
        return VocabularyNotebookService(db).bookmark_from_conversation(secure_payload)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{entry_id}", response_model=VocabularyEntryResponse)
async def update_vocabulary_entry(
    entry_id: int,
    payload: VocabularyEntryUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VocabularyEntryResponse:
    try:
        return VocabularyNotebookService(db).update_entry(entry_id, payload, user_id=current_user.id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{entry_id}/review", response_model=VocabularyEntryResponse)
async def record_vocabulary_review(
    entry_id: int,
    payload: VocabularyReviewRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VocabularyEntryResponse:
    try:
        return VocabularyNotebookService(db).record_review(entry_id, payload, user_id=current_user.id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/stats", response_model=VocabularyNotebookStatsResponse)
async def get_vocabulary_stats(
    session_id: str = Query(..., min_length=1),
    user_id: int | None = Query(default=None, ge=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VocabularyNotebookStatsResponse:
    return VocabularyNotebookService(db).stats(session_id=authenticated_session_id(current_user), user_id=current_user.id)


@router.post("/review-sessions", response_model=VocabularyReviewSessionResponse)
async def create_vocabulary_review_session(
    payload: VocabularyReviewSessionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VocabularyReviewSessionResponse:
    secure_payload = payload.model_copy(
        update={"session_id": authenticated_session_id(current_user), "user_id": current_user.id}
    )
    return VocabularyNotebookService(db).create_review_session(secure_payload)


@router.get("/review-sessions/{review_session_id}", response_model=VocabularyReviewSessionResponse)
async def get_vocabulary_review_session(
    review_session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VocabularyReviewSessionResponse:
    try:
        return VocabularyNotebookService(db).get_review_session(review_session_id, user_id=current_user.id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/review-sessions/{review_session_id}/submit", response_model=VocabularyReviewSessionResponse)
async def submit_vocabulary_review_session(
    review_session_id: int,
    payload: VocabularyReviewSessionSubmit,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VocabularyReviewSessionResponse:
    try:
        return VocabularyNotebookService(db).submit_review_session(review_session_id, payload, user_id=current_user.id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
