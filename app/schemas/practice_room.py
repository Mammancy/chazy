from datetime import datetime

from pydantic import BaseModel


class PracticeRoomResponse(BaseModel):
    id: int
    session_id: int
    room_code: str
    started_at: datetime | None
    ended_at: datetime | None
    status: str


class PracticeTopicResponse(BaseModel):
    category: str
    prompt: str
    follow_ups: list[str]
