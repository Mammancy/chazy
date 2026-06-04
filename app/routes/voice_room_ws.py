from __future__ import annotations

import json

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.user import User
from app.services.realtime_practice_service import PracticeRoomManager
from app.services.token_service import TokenError, TokenService
from app.services.voice_room_service import voice_room_signaling_manager

router = APIRouter(tags=["voice-room-websocket"])


@router.websocket("/ws/voice-rooms/{room_id}")
async def voice_room_websocket(websocket: WebSocket, room_id: int, db: Session = Depends(get_db)) -> None:
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    user: User | None = None
    try:
        try:
            user_id = TokenService.decode_access_token(token)
        except TokenError:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        user = db.get(User, user_id)
        if user is None or not user.is_active:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        try:
            PracticeRoomManager(db).authorize_room(room_id=room_id, user_id=user.id)
        except (PermissionError, ValueError):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        await voice_room_signaling_manager.connect(room_id=room_id, user=user, websocket=websocket)
        while True:
            raw_payload = await websocket.receive_text()
            try:
                payload = json.loads(raw_payload)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid voice room signal."})
                continue
            await voice_room_signaling_manager.relay(room_id=room_id, user=user, payload=payload)
    except WebSocketDisconnect:
        pass
    finally:
        if user is not None:
            await voice_room_signaling_manager.disconnect(room_id=room_id, user=user)
