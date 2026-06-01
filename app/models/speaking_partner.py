from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SpeakingPartnerProfile(Base):
    __tablename__ = "speaking_partner_profiles"
    __table_args__ = (UniqueConstraint("user_id", name="uq_speaking_partner_profiles_user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    speaking_level: Mapped[str] = mapped_column(String(32), default="beginner", index=True)
    native_language: Mapped[str] = mapped_column(String(80), default="", index=True)
    target_language: Mapped[str] = mapped_column(String(80), default="English", index=True)
    interests: Mapped[list[str]] = mapped_column(JSON, default=list)
    timezone: Mapped[str] = mapped_column(String(64), default="Africa/Lagos", index=True)
    availability: Mapped[dict] = mapped_column(JSON, default=dict)
    bio: Mapped[str] = mapped_column(Text, default="")
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class PracticeRequest(Base):
    __tablename__ = "practice_requests"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    sender_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    receiver_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
