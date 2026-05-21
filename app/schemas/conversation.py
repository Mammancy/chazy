from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ConversationStatus = Literal["active", "archived", "closed"]


class ConversationBase(BaseModel):
    title: str = Field(default="New Conversation", max_length=255)
    summary: str | None = None
    status: ConversationStatus = "active"


class ConversationCreate(ConversationBase):
    user_id: int


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    summary: str | None = None
    status: ConversationStatus | None = None


class ConversationRead(ConversationBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

