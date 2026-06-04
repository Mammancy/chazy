from __future__ import annotations

import json

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.user import User
from app.services.realtime_practice_service import PracticeRoomManager, connection_manager
from app.services.token_service import TokenError, TokenService

router = APIRouter(tags=["practice-room-websocket"])


@router.websocket("/ws/practice-rooms/{room_id}")
async def practice_room_websocket(websocket: WebSocket, room_id: int, db: Session = Depends(get_db)) -> None:
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

        room_manager = PracticeRoomManager(db)
        try:
            room, _ = room_manager.authorize_room(room_id=room_id, user_id=user.id)
        except PermissionError:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        except ValueError:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        await connection_manager.connect(room_id=room.id, user=user, websocket=websocket)
        while True:
            raw_payload = await websocket.receive_text()
            try:
                payload = json.loads(raw_payload)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid message payload."})
                continue

            event_type = payload.get("type")
            if event_type == "typing":
                await connection_manager.broadcast_typing(
                    room_id=room.id,
                    user=user,
                    is_typing=bool(payload.get("isTyping") or payload.get("is_typing")),
                )
                continue

            if event_type == "message":
                content = str(payload.get("content") or "")
                try:
                    message = room_manager.persist_message(room=room, sender=user, content=content)
                except ValueError as exc:
                    await websocket.send_json({"type": "error", "message": str(exc)})
                    continue
                await connection_manager.broadcast(
                    room_id=room.id,
                    payload={"type": "message", "message": message.model_dump(mode="json")},
                )
                continue

            await websocket.send_json({"type": "error", "message": "Unsupported practice room event."})
    except WebSocketDisconnect:
        pass
    finally:
        if user is not None:
            await connection_manager.disconnect(room_id=room_id, user_id=user.id)
