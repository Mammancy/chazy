from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SpeakingChallenge(Base):
    __tablename__ = "speaking_challenges"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    difficulty: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(160))
    prompt: Mapped[str] = mapped_column(Text)
    suggested_duration_seconds: Mapped[int] = mapped_column(Integer, default=60)
    focus_area: Mapped[str] = mapped_column(String(120), default="fluency")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SpeakingChallengeCompletion(Base):
    __tablename__ = "speaking_challenge_completions"
    __table_args__ = (
        UniqueConstraint(
            "client_session_id",
            "user_id",
            "challenge_date",
            "difficulty",
            name="uq_speaking_completion_daily",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    challenge_id: Mapped[int] = mapped_column(ForeignKey("speaking_challenges.id"), index=True)
    client_session_id: Mapped[str] = mapped_column(String(128), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    difficulty: Mapped[str] = mapped_column(String(32), index=True)
    challenge_date: Mapped[date] = mapped_column(Date, index=True)
    spoken_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reflection: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
