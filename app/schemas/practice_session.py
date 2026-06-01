from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


PracticeSessionStatus = Literal["scheduled", "completed", "cancelled", "missed"]


class PracticeSessionCreate(BaseModel):
    request_id: int = Field(..., ge=1)
    scheduled_at: datetime
    duration_minutes: int = Field(..., ge=15, le=180)
    topic: str = Field(default="", max_length=180)
    notes: str = Field(default="", max_length=1000)


class PracticeSessionUpdate(BaseModel):
    scheduled_at: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=15, le=180)
    topic: str | None = Field(default=None, max_length=180)
    notes: str | None = Field(default=None, max_length=1000)
    status: PracticeSessionStatus | None = None


class PracticeSessionFeedback(BaseModel):
    feedback: str = Field(default="", max_length=1000)


class PracticeSessionUserSummary(BaseModel):
    id: int
    display_name: str
    initials: str


class PracticeSessionResponse(BaseModel):
    id: int
    requester_user_id: int
    partner_user_id: int
    request_id: int
    scheduled_at: datetime
    duration_minutes: int
    topic: str
    notes: str
    status: PracticeSessionStatus
    feedback_requester: str
    feedback_partner: str
    requester: PracticeSessionUserSummary
    partner: PracticeSessionUserSummary
    xp_awarded: int
    created_at: datetime
    updated_at: datetime


class PracticeSessionListResponse(BaseModel):
    sessions: list[PracticeSessionResponse]
