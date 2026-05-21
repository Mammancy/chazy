from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserBase(BaseModel):
    external_id: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=255)
    full_name: str | None = Field(default=None, max_length=255)
    timezone: str = Field(default="Africa/Lagos", max_length=64)
    is_active: bool = True


class UserCreate(UserBase):
    pass


class UserUpdate(BaseModel):
    external_id: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=255)
    full_name: str | None = Field(default=None, max_length=255)
    timezone: str | None = Field(default=None, max_length=64)
    is_active: bool | None = None


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime

