from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EmotionalMemoryBase(BaseModel):
    emotion: str = Field(..., min_length=1, max_length=64)
    intensity: float = Field(default=0.5, ge=0.0, le=1.0)
    trigger_text: str | None = None
    notes: str | None = None
    metadata_json: dict | None = None


class EmotionalMemoryCreate(EmotionalMemoryBase):
    user_id: int
    conversation_id: int | None = None
    message_id: int | None = None


class EmotionalMemoryUpdate(BaseModel):
    emotion: str | None = Field(default=None, min_length=1, max_length=64)
    intensity: float | None = Field(default=None, ge=0.0, le=1.0)
    trigger_text: str | None = None
    notes: str | None = None
    metadata_json: dict | None = None


class EmotionalMemoryRead(EmotionalMemoryBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    conversation_id: int | None
    message_id: int | None
    created_at: datetime
    updated_at: datetime

