from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MessageRole = Literal["user", "assistant", "system", "tool"]


class MessageBase(BaseModel):
    role: MessageRole
    content: str = Field(..., min_length=1)
    token_count: int | None = Field(default=None, ge=0)


class MessageCreate(MessageBase):
    conversation_id: int
    user_id: int | None = None


class MessageUpdate(BaseModel):
    content: str | None = Field(default=None, min_length=1)
    token_count: int | None = Field(default=None, ge=0)


class MessageRead(MessageBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    user_id: int | None
    created_at: datetime

