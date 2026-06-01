from __future__ import annotations

import random
import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.practice_room import PracticeRoom
from app.models.practice_session import PracticeSession
from app.schemas.practice_room import PracticeRoomResponse, PracticeTopicResponse


PRACTICE_TOPICS = [
    ("Public Speaking", "Introduce yourself", ["What should people remember about you?", "How can you sound more confident?"]),
    ("Public Speaking", "Describe your dream job", ["Why does that job matter to you?", "What skills would help you succeed?"]),
    ("Public Speaking", "Tell a story about a challenge", ["What happened first?", "What did you learn?"]),
    ("Interviews", "Tell me about yourself", ["What experience is most relevant?", "How can you end strongly?"]),
    ("Interviews", "Why should we hire you?", ["What strength can you prove?", "What example supports it?"]),
    ("Daily Conversation", "Favorite food", ["When do you usually eat it?", "How would you describe the taste?"]),
    ("Daily Conversation", "Weekend plans", ["Who will you spend time with?", "What are you looking forward to?"]),
    ("Daily Conversation", "Travel experiences", ["Where did you go?", "What surprised you?"]),
    ("Leadership", "Describe a difficult decision", ["What options did you consider?", "How did you decide?"]),
    ("Leadership", "Managing a team conflict", ["What caused the conflict?", "How did you keep communication respectful?"]),
]


class PracticeRoomService:
    def __init__(self, db: Session):
        self.db = db

    def create_room(self, *, session_id: int, user_id: int) -> PracticeRoomResponse:
        self._authorized_session(session_id=session_id, user_id=user_id)
        room = self._room_for_session(session_id)
        if room is None:
            room = PracticeRoom(session_id=session_id, room_code=self._room_code(), status="scheduled")
            self.db.add(room)
            self.db.commit()
            self.db.refresh(room)
        return self._response(room)

    def get_room(self, *, session_id: int, user_id: int) -> PracticeRoomResponse:
        self._authorized_session(session_id=session_id, user_id=user_id)
        room = self._room_for_session(session_id)
        if room is None:
            raise ValueError("Practice room not found.")
        return self._response(room)

    def start_room(self, *, session_id: int, user_id: int) -> PracticeRoomResponse:
        self._authorized_session(session_id=session_id, user_id=user_id)
        room = self._room_for_session(session_id)
        if room is None:
            room = PracticeRoom(session_id=session_id, room_code=self._room_code())
        room.status = "active"
        room.started_at = room.started_at or datetime.now(timezone.utc)
        room.ended_at = None
        self.db.add(room)
        self.db.commit()
        self.db.refresh(room)
        return self._response(room)

    def end_room(self, *, session_id: int, user_id: int) -> PracticeRoomResponse:
        self._authorized_session(session_id=session_id, user_id=user_id)
        room = self._room_for_session(session_id)
        if room is None:
            raise ValueError("Practice room not found.")
        room.status = "ended"
        room.ended_at = datetime.now(timezone.utc)
        self.db.add(room)
        self.db.commit()
        self.db.refresh(room)
        return self._response(room)

    def random_topic(self) -> PracticeTopicResponse:
        category, prompt, follow_ups = random.choice(PRACTICE_TOPICS)
        return PracticeTopicResponse(category=category, prompt=prompt, follow_ups=follow_ups)

    def _authorized_session(self, *, session_id: int, user_id: int) -> PracticeSession:
        session = self.db.get(PracticeSession, session_id)
        if session is None:
            raise ValueError("Practice session not found.")
        if user_id not in {session.requester_user_id, session.partner_user_id}:
            raise PermissionError("Only session participants can access this practice room.")
        return session

    def _room_for_session(self, session_id: int) -> PracticeRoom | None:
        return self.db.scalar(select(PracticeRoom).where(PracticeRoom.session_id == session_id))

    def _room_code(self) -> str:
        while True:
            code = f"CONF-{secrets.token_hex(3).upper()}"
            if self.db.scalar(select(PracticeRoom).where(PracticeRoom.room_code == code)) is None:
                return code

    @staticmethod
    def _response(room: PracticeRoom) -> PracticeRoomResponse:
        return PracticeRoomResponse(
            id=room.id,
            session_id=room.session_id,
            room_code=room.room_code,
            started_at=room.started_at,
            ended_at=room.ended_at,
            status=room.status,
        )
