import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.chat import ChatRequest, ChatResponse, ConversationHistoryResponse
from app.services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)


@router.post("/", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
) -> ChatResponse:
    service = ChatService(db)
    client_request_id = request.headers.get("X-Client-Request-ID") or str(uuid4())

    logger.info(
        "chat_request start request_id=%s session_id=%s conversation_id=%s",
        client_request_id,
        payload.session_id,
        payload.conversation_id,
    )

    result = await service.process_message(payload, request_id=client_request_id)
    response.headers["X-Backend-Request-ID"] = client_request_id

    logger.info(
        "chat_request done request_id=%s status=%s user_id=%s conversation_id=%s",
        client_request_id,
        result.status,
        result.user_id,
        result.conversation_id,
    )

    return result


@router.get("/history", response_model=ConversationHistoryResponse)
async def get_chat_history(
    session_id: str = Query(..., min_length=1),
    conversation_id: int | None = Query(default=None, ge=1),
    user_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> ConversationHistoryResponse:
    service = ChatService(db)
    return service.get_conversation_history(
        session_id=session_id,
        conversation_id=conversation_id,
        user_id=user_id,
        limit=limit,
        offset=offset,
    )


@router.get("/history/{conversation_id}", response_model=ConversationHistoryResponse)
async def get_chat_history_by_conversation(
    conversation_id: int,
    session_id: str = Query(..., min_length=1),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> ConversationHistoryResponse:
    service = ChatService(db)
    return service.get_conversation_history(
        session_id=session_id,
        conversation_id=conversation_id,
        user_id=user_id,
        limit=limit,
        offset=offset,
    )

