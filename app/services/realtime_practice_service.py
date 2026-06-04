from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.practice_room import PracticeRoom
from app.models.practice_room_message import PracticeRoomMessage
from app.models.practice_session import PracticeSession
from app.models.user import User
from app.schemas.practice_room import (
    PracticeRoomMessageResponse,
    PracticeRoomMessagesResponse,
    PracticeRoomMessageSender,
)


@dataclass(frozen=True)
class RoomParticipant:
    user_id: int
    display_name: str
    initials: str


class PracticeRoomConnectionManager:
    def __init__(self) -> None:
        self.active_connections: dict[int, dict[int, WebSocket]] = {}
        self.participants: dict[int, dict[int, RoomParticipant]] = {}
        self.typing_users: dict[int, set[int]] = {}

    async def connect(self, *, room_id: int, user: User, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.setdefault(room_id, {})[user.id] = websocket
        self.participants.setdefault(room_id, {})[user.id] = RoomParticipant(
            user_id=user.id,
            display_name=_display_name(user),
            initials=_initials(user),
        )
        await self.broadcast_presence(room_id)

    async def disconnect(self, *, room_id: int, user_id: int) -> None:
        self.active_connections.get(room_id, {}).pop(user_id, None)
        self.participants.get(room_id, {}).pop(user_id, None)
        self.typing_users.get(room_id, set()).discard(user_id)
        if not self.active_connections.get(room_id):
            self.active_connections.pop(room_id, None)
            self.participants.pop(room_id, None)
            self.typing_users.pop(room_id, None)
            return
        await self.broadcast_presence(room_id)

    async def broadcast(self, *, room_id: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, default=str)
        stale_user_ids: list[int] = []
        for user_id, websocket in list(self.active_connections.get(room_id, {}).items()):
            try:
                await websocket.send_text(encoded)
            except RuntimeError:
                stale_user_ids.append(user_id)
        for user_id in stale_user_ids:
            await self.disconnect(room_id=room_id, user_id=user_id)

    async def broadcast_presence(self, room_id: int) -> None:
        users = [
            {
                "user_id": participant.user_id,
                "display_name": participant.display_name,
                "initials": participant.initials,
            }
            for participant in self.participants.get(room_id, {}).values()
        ]
        await self.broadcast(room_id=room_id, payload={"type": "presence", "users": users})

    async def broadcast_typing(self, *, room_id: int, user: User, is_typing: bool) -> None:
        room_typing = self.typing_users.setdefault(room_id, set())
        if is_typing:
            room_typing.add(user.id)
        else:
            room_typing.discard(user.id)
        await self.broadcast(
            room_id=room_id,
            payload={
                "type": "typing",
                "user_id": user.id,
                "display_name": _display_name(user),
                "is_typing": is_typing,
            },
        )


class PracticeRoomManager:
    def __init__(self, db: Session):
        self.db = db

    def authorize_room(self, *, room_id: int, user_id: int) -> tuple[PracticeRoom, PracticeSession]:
        room = self.db.get(PracticeRoom, room_id)
        if room is None:
            raise ValueError("Practice room not found.")
        session = self.db.get(PracticeSession, room.session_id)
        if session is None:
            raise ValueError("Practice session not found.")
        if user_id not in {session.requester_user_id, session.partner_user_id}:
            raise PermissionError("Only session participants can access this practice room.")
        return room, session

    def authorize_session(self, *, session_id: int, user_id: int) -> PracticeSession:
        session = self.db.get(PracticeSession, session_id)
        if session is None:
            raise ValueError("Practice session not found.")
        if user_id not in {session.requester_user_id, session.partner_user_id}:
            raise PermissionError("Only session participants can access this practice room.")
        return session

    def list_messages(self, *, session_id: int, user_id: int) -> PracticeRoomMessagesResponse:
        self.authorize_session(session_id=session_id, user_id=user_id)
        messages = self.db.scalars(
            select(PracticeRoomMessage)
            .where(PracticeRoomMessage.session_id == session_id)
            .order_by(PracticeRoomMessage.created_at.asc(), PracticeRoomMessage.id.asc())
        ).all()
        return PracticeRoomMessagesResponse(messages=[self._message_response(message) for message in messages])

    def persist_message(
        self,
        *,
        room: PracticeRoom,
        sender: User,
        content: str,
        message_type: str = "message",
    ) -> PracticeRoomMessageResponse:
        clean_content = content.strip()
        if not clean_content:
            raise ValueError("Message content is required.")
        message = PracticeRoomMessage(
            room_id=room.id,
            session_id=room.session_id,
            sender_user_id=sender.id,
            content=clean_content[:2000],
            message_type=message_type,
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return self._message_response(message)

    def _message_response(self, message: PracticeRoomMessage) -> PracticeRoomMessageResponse:
        sender = self.db.get(User, message.sender_user_id)
        return PracticeRoomMessageResponse(
            id=message.id,
            room_id=message.room_id,
            session_id=message.session_id,
            sender_user_id=message.sender_user_id,
            sender=PracticeRoomMessageSender(
                id=message.sender_user_id,
                display_name=_display_name(sender),
                initials=_initials(sender),
            ),
            content=message.content,
            message_type=message.message_type,
            created_at=_aware(message.created_at),
        )


connection_manager = PracticeRoomConnectionManager()


def _display_name(user: User | None) -> str:
    if user is None:
        return "Confidence learner"
    return user.full_name or user.email or f"Learner {user.id}"


def _initials(user: User | None) -> str:
    name = _display_name(user)
    parts = [part[0].upper() for part in name.split() if part]
    if len(parts) >= 2:
        return "".join(parts[:2])
    if parts:
        return parts[0]
    return "CL"


def _aware(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
