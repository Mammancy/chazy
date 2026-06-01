from datetime import datetime

from pydantic import BaseModel

from app.schemas.user import SignUpRequest


class AdminUserSummaryResponse(BaseModel):
    id: int
    email: str | None
    full_name: str | None
    phone_number: str | None
    country: str | None
    state: str | None
    timezone: str
    is_active: bool
    public_profile_visible: bool
    created_at: datetime
    updated_at: datetime
    conversation_count: int
    message_count: int
    last_activity_at: datetime | None


class AdminUserListResponse(BaseModel):
    users: list[AdminUserSummaryResponse]
    total: int
    limit: int
    offset: int


class AdminUserActivityResponse(BaseModel):
    type: str
    title: str
    detail: str
    occurred_at: datetime


class AdminUserProfileResponse(BaseModel):
    user: AdminUserSummaryResponse
    activity_history: list[AdminUserActivityResponse]


class AdminUserStatusUpdate(BaseModel):
    is_active: bool | None = None
    public_profile_visible: bool | None = None


class AdminUserStatusResponse(BaseModel):
    success: bool
    message: str
    user: AdminUserSummaryResponse


class AdminCreateRequest(SignUpRequest):
    pass
