import asyncio
import json
import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.auth import authenticated_session_id, get_current_user
from app.models.user import User
from app.schemas.chat import ChatRequest, ChatResponse, ConversationHistoryResponse
from app.services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)


@router.post("/", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatResponse:
    service = ChatService(db)
    client_request_id = request.headers.get("X-Client-Request-ID") or str(uuid4())
    secure_payload = payload.model_copy(
        update={"session_id": authenticated_session_id(current_user), "user_id": current_user.id}
    )

    logger.info(
        "chat_request start request_id=%s session_id=%s conversation_id=%s",
        client_request_id,
        secure_payload.session_id,
        secure_payload.conversation_id,
    )

    result = await service.process_message(secure_payload, request_id=client_request_id)
    response.headers["X-Backend-Request-ID"] = client_request_id

    logger.info(
        "chat_request done request_id=%s status=%s user_id=%s conversation_id=%s",
        client_request_id,
        result.status,
        result.user_id,
        result.conversation_id,
    )

    return result


@router.post("/stream")
async def chat_stream(
    payload: ChatRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    service = ChatService(db)
    client_request_id = request.headers.get("X-Client-Request-ID") or str(uuid4())
    secure_payload = payload.model_copy(
        update={"session_id": authenticated_session_id(current_user), "user_id": current_user.id}
    )

    async def event_stream():
        try:
            result = await service.process_message(secure_payload, request_id=client_request_id)
            partial = ""
            for word in result.assistant_message.split():
                partial = f"{partial} {word}".strip()
                yield _stream_event("partial", {"text": partial, "request_id": client_request_id})
                await asyncio.sleep(0.035)
            yield _stream_event("final", result.model_dump(mode="json"))
        except Exception as exc:
            logger.exception("chat_stream failed request_id=%s", client_request_id)
            yield _stream_event("error", {"message": str(exc), "request_id": client_request_id})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Backend-Request-ID": client_request_id,
        },
    )


def _stream_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.get("/history", response_model=ConversationHistoryResponse)
async def get_chat_history(
    session_id: str = Query(..., min_length=1),
    conversation_id: int | None = Query(default=None, ge=1),
    user_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConversationHistoryResponse:
    service = ChatService(db)
    return service.get_conversation_history(
        session_id=authenticated_session_id(current_user),
        conversation_id=conversation_id,
        user_id=current_user.id,
        limit=limit,
        offset=offset,
    )


@router.get("/history/{conversation_id}", response_model=ConversationHistoryResponse)
async def get_chat_history_by_conversation(
    conversation_id: int,
    session_id: str = Query(..., min_length=1),
    user_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConversationHistoryResponse:
    service = ChatService(db)
    return service.get_conversation_history(
        session_id=authenticated_session_id(current_user),
        conversation_id=conversation_id,
        user_id=current_user.id,
        limit=limit,
        offset=offset,
    )
