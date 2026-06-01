from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.practice_session import (
    PracticeSessionCreate,
    PracticeSessionFeedback,
    PracticeSessionListResponse,
    PracticeSessionResponse,
    PracticeSessionUpdate,
)
from app.schemas.practice_room import PracticeRoomResponse
from app.services.practice_room_service import PracticeRoomService
from app.services.practice_session_service import PracticeSessionService

router = APIRouter(prefix="/practice-sessions", tags=["practice-sessions"])


@router.post("", response_model=PracticeSessionResponse)
async def create_practice_session(
    payload: PracticeSessionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PracticeSessionResponse:
    try:
        return PracticeSessionService(db).create(user=current_user, payload=payload)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=PracticeSessionListResponse)
async def list_practice_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PracticeSessionListResponse:
    return PracticeSessionService(db).list(user_id=current_user.id)


@router.post("/{session_id}/room", response_model=PracticeRoomResponse)
async def create_practice_room(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PracticeRoomResponse:
    try:
        return PracticeRoomService(db).create_room(session_id=session_id, user_id=current_user.id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{session_id}/room", response_model=PracticeRoomResponse)
async def get_practice_room(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PracticeRoomResponse:
    try:
        return PracticeRoomService(db).get_room(session_id=session_id, user_id=current_user.id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{session_id}/room/start", response_model=PracticeRoomResponse)
async def start_practice_room(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PracticeRoomResponse:
    try:
        return PracticeRoomService(db).start_room(session_id=session_id, user_id=current_user.id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{session_id}/room/end", response_model=PracticeRoomResponse)
async def end_practice_room(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PracticeRoomResponse:
    try:
        return PracticeRoomService(db).end_room(session_id=session_id, user_id=current_user.id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{session_id}", response_model=PracticeSessionResponse)
async def get_practice_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PracticeSessionResponse:
    try:
        return PracticeSessionService(db).get(session_id=session_id, user_id=current_user.id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{session_id}", response_model=PracticeSessionResponse)
async def update_practice_session(
    session_id: int,
    payload: PracticeSessionUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PracticeSessionResponse:
    try:
        return PracticeSessionService(db).update(session_id=session_id, user_id=current_user.id, payload=payload)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@router.patch("/{session_id}/complete", response_model=PracticeSessionResponse)
async def complete_practice_session(
    session_id: int,
    payload: PracticeSessionFeedback,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PracticeSessionResponse:
    try:
        return PracticeSessionService(db).complete(session_id=session_id, user=current_user, payload=payload)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/{session_id}/cancel", response_model=PracticeSessionResponse)
async def cancel_practice_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PracticeSessionResponse:
    try:
        return PracticeSessionService(db).cancel(session_id=session_id, user_id=current_user.id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
