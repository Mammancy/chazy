from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class PronunciationExercise(Base):
    __tablename__ = "pronunciation_exercises"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    word: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    phonetic_spelling: Mapped[str] = mapped_column(String(160), default="")
    difficulty: Mapped[str] = mapped_column(String(32), default="beginner", index=True)
    audio_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    example_sentences: Mapped[list[str]] = mapped_column(JSON, default=list)
    pronunciation_tips: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    attempts: Mapped[list["PronunciationPracticeAttempt"]] = relationship(back_populates="exercise")


class PronunciationPracticeSession(Base):
    __tablename__ = "pronunciation_practice_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    client_session_id: Mapped[str] = mapped_column(String(128), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    target_word_count: Mapped[int] = mapped_column(Integer, default=0)
    current_word_index: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    attempts: Mapped[list["PronunciationPracticeAttempt"]] = relationship(
        back_populates="practice_session",
        cascade="all, delete-orphan",
    )


class PronunciationPracticeAttempt(Base):
    __tablename__ = "pronunciation_practice_attempts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    practice_session_id: Mapped[int] = mapped_column(
        ForeignKey("pronunciation_practice_sessions.id"),
        index=True,
    )
    exercise_id: Mapped[int] = mapped_column(ForeignKey("pronunciation_exercises.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    recorded_audio_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    scoring_status: Mapped[str] = mapped_column(String(32), default="not_scored", index=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    practice_session: Mapped["PronunciationPracticeSession"] = relationship(back_populates="attempts")
    exercise: Mapped["PronunciationExercise"] = relationship(back_populates="attempts")
