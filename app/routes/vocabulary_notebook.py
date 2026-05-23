from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.vocabulary_notebook import (
    VocabularyBookmarkFromConversationRequest,
    VocabularyEntryCreate,
    VocabularyEntryResponse,
    VocabularyEntryUpdate,
    VocabularyNotebookResponse,
    VocabularyNotebookStatsResponse,
    VocabularyReviewRequest,
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
    db: Session = Depends(get_db),
) -> VocabularyNotebookResponse:
    return VocabularyNotebookService(db).list_entries(
        session_id=session_id,
        user_id=user_id,
        mastery_status=mastery_status,
        bookmarked=bookmarked,
        due_only=due_only,
    )


@router.post("/", response_model=VocabularyEntryResponse)
async def create_vocabulary_entry(
    payload: VocabularyEntryCreate,
    db: Session = Depends(get_db),
) -> VocabularyEntryResponse:
    return VocabularyNotebookService(db).create_entry(payload)


@router.post("/bookmark-from-conversation", response_model=VocabularyEntryResponse)
async def bookmark_word_from_conversation(
    payload: VocabularyBookmarkFromConversationRequest,
    db: Session = Depends(get_db),
) -> VocabularyEntryResponse:
    try:
        return VocabularyNotebookService(db).bookmark_from_conversation(payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{entry_id}", response_model=VocabularyEntryResponse)
async def update_vocabulary_entry(
    entry_id: int,
    payload: VocabularyEntryUpdate,
    db: Session = Depends(get_db),
) -> VocabularyEntryResponse:
    try:
        return VocabularyNotebookService(db).update_entry(entry_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{entry_id}/review", response_model=VocabularyEntryResponse)
async def record_vocabulary_review(
    entry_id: int,
    payload: VocabularyReviewRequest,
    db: Session = Depends(get_db),
) -> VocabularyEntryResponse:
    try:
        return VocabularyNotebookService(db).record_review(entry_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/stats", response_model=VocabularyNotebookStatsResponse)
async def get_vocabulary_stats(
    session_id: str = Query(..., min_length=1),
    user_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> VocabularyNotebookStatsResponse:
    return VocabularyNotebookService(db).stats(session_id=session_id, user_id=user_id)
