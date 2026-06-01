from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


PracticeRequestStatus = Literal["pending", "accepted", "rejected", "completed"]


class SpeakingPartnerProfileUpdate(BaseModel):
    speaking_level: str | None = Field(default=None, max_length=32)
    native_language: str | None = Field(default=None, max_length=80)
    target_language: str | None = Field(default=None, max_length=80)
    interests: list[str] | None = None
    timezone: str | None = Field(default=None, max_length=64)
    availability: dict[str, Any] | None = None
    bio: str | None = Field(default=None, max_length=800)
    is_public: bool | None = None


class SpeakingPartnerProfileResponse(BaseModel):
    id: int
    user_id: int
    display_name: str
    initials: str
    speaking_level: str
    native_language: str
    target_language: str
    interests: list[str]
    timezone: str
    availability: dict[str, Any]
    bio: str
    is_public: bool
    created_at: datetime
    updated_at: datetime


class SpeakingPartnerListResponse(BaseModel):
    partners: list[SpeakingPartnerProfileResponse]


class RecommendedSpeakingPartnerResponse(SpeakingPartnerProfileResponse):
    match_score: int
    shared_interests: list[str]
    match_reasons: list[str]


class RecommendedSpeakingPartnerListResponse(BaseModel):
    partners: list[RecommendedSpeakingPartnerResponse]


class PracticeRequestCreate(BaseModel):
    receiver_user_id: int = Field(..., ge=1)
    message: str = Field(default="", max_length=500)


class PracticeRequestUpdate(BaseModel):
    status: PracticeRequestStatus


class PracticeRequestUserSummary(BaseModel):
    id: int
    display_name: str
    initials: str
    speaking_level: str | None = None
    timezone: str | None = None


class PracticeRequestResponse(BaseModel):
    id: int
    sender_user_id: int
    receiver_user_id: int
    status: PracticeRequestStatus
    message: str
    sender: PracticeRequestUserSummary
    receiver: PracticeRequestUserSummary
    created_at: datetime


class PracticeRequestListResponse(BaseModel):
    incoming: list[PracticeRequestResponse]
    outgoing: list[PracticeRequestResponse]
