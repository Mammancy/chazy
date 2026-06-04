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


class PracticeRoomMessageSender(BaseModel):
    id: int
    display_name: str
    initials: str


class PracticeRoomMessageResponse(BaseModel):
    id: int
    room_id: int
    session_id: int
    sender_user_id: int
    sender: PracticeRoomMessageSender
    content: str
    message_type: str
    created_at: datetime


class PracticeRoomMessagesResponse(BaseModel):
    messages: list[PracticeRoomMessageResponse]
