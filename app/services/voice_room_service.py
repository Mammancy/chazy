from __future__ import annotations

import json
from typing import Any

from fastapi import WebSocket

from app.models.user import User


VOICE_SIGNAL_TYPES = {"join", "leave", "offer", "answer", "ice-candidate", "mute", "unmute"}


class VoiceRoomSignalingManager:
    def __init__(self) -> None:
        self.active_connections: dict[int, dict[int, WebSocket]] = {}

    async def connect(self, *, room_id: int, user: User, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.setdefault(room_id, {})[user.id] = websocket
        await self.send_to_room(
            room_id=room_id,
            sender_user_id=user.id,
            payload=self._event_payload(event_type="join", user=user),
        )

    async def disconnect(self, *, room_id: int, user: User) -> None:
        self.active_connections.get(room_id, {}).pop(user.id, None)
        if not self.active_connections.get(room_id):
            self.active_connections.pop(room_id, None)
            return
        await self.send_to_room(
            room_id=room_id,
            sender_user_id=user.id,
            payload=self._event_payload(event_type="leave", user=user),
        )

    async def relay(self, *, room_id: int, user: User, payload: dict[str, Any]) -> None:
        event_type = str(payload.get("type") or "")
        if event_type not in VOICE_SIGNAL_TYPES:
            await self.send_to_user(
                room_id=room_id,
                user_id=user.id,
                payload={"type": "error", "message": "Unsupported voice room event."},
            )
            return

        await self.send_to_room(
            room_id=room_id,
            sender_user_id=user.id,
            payload={
                **payload,
                "type": event_type,
                "sender_user_id": user.id,
                "sender": self._user_payload(user),
            },
        )

    async def send_to_user(self, *, room_id: int, user_id: int, payload: dict[str, Any]) -> None:
        websocket = self.active_connections.get(room_id, {}).get(user_id)
        if websocket is None:
            return
        await websocket.send_text(json.dumps(payload, default=str))

    async def send_to_room(self, *, room_id: int, sender_user_id: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, default=str)
        stale_user_ids: list[int] = []
        for user_id, websocket in list(self.active_connections.get(room_id, {}).items()):
            if user_id == sender_user_id:
                continue
            try:
                await websocket.send_text(encoded)
            except RuntimeError:
                stale_user_ids.append(user_id)
        for user_id in stale_user_ids:
            self.active_connections.get(room_id, {}).pop(user_id, None)

    def _event_payload(self, *, event_type: str, user: User) -> dict[str, Any]:
        return {
            "type": event_type,
            "sender_user_id": user.id,
            "sender": self._user_payload(user),
        }

    @staticmethod
    def _user_payload(user: User) -> dict[str, Any]:
        display_name = user.full_name or user.email or f"Learner {user.id}"
        initials = "".join(part[0] for part in display_name.split() if part)[:2].upper() or "CL"
        return {
            "id": user.id,
            "display_name": display_name,
            "initials": initials,
        }


voice_room_signaling_manager = VoiceRoomSignalingManager()
