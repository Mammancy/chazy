from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ResponseLengthPreference = Literal["SHORT", "MEDIUM", "DETAILED"]


class UserBase(BaseModel):
    external_id: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=255)
    full_name: str | None = Field(default=None, max_length=255)
    phone_number: str | None = Field(default=None, max_length=32)
    country: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    timezone: str = Field(default="Africa/Lagos", max_length=64)
    response_length_preference: ResponseLengthPreference = "SHORT"
    is_active: bool = True


class UserCreate(UserBase):
    password: str | None = Field(default=None, min_length=6, max_length=128)


class UserUpdate(BaseModel):
    external_id: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=255)
    full_name: str | None = Field(default=None, max_length=255)
    phone_number: str | None = Field(default=None, max_length=32)
    country: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    timezone: str | None = Field(default=None, max_length=64)
    response_length_preference: ResponseLengthPreference | None = None
    is_active: bool | None = None


class ResponseLengthPreferenceUpdate(BaseModel):
    response_length_preference: ResponseLengthPreference


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class SignUpRequest(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., min_length=3, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    phone_number: str = Field(..., min_length=3, max_length=32)
    country: str = Field(..., min_length=1, max_length=100)
    state: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=6, max_length=128)


class SignInRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(..., min_length=1, max_length=128)


class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=16, max_length=255)
    new_password: str = Field(..., min_length=6, max_length=128)


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., min_length=20)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class BasicResponse(BaseModel):
    success: bool
    message: str


class AuthResponse(BaseModel):
    success: bool
    message: str
    user: UserRead
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
