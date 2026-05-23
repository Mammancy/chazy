from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class VocabularyNotebookEntry(Base):
    __tablename__ = "vocabulary_notebook_entries"
    __table_args__ = (
        UniqueConstraint("session_id", "user_id", "word", name="uq_vocabulary_notebook_word"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    session_id: Mapped[str] = mapped_column(String(128), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    source_message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id"), nullable=True, index=True)
    word: Mapped[str] = mapped_column(String(120), index=True)
    meaning: Mapped[str] = mapped_column(Text)
    example_sentence: Mapped[str] = mapped_column(Text)
    mastery_status: Mapped[str] = mapped_column(String(32), default="new", index=True)
    review_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    retention_score: Mapped[float] = mapped_column(Float, default=0.0)
    ease_factor: Mapped[float] = mapped_column(Float, default=2.5)
    review_interval_days: Mapped[int] = mapped_column(Integer, default=1)
    consecutive_correct: Mapped[int] = mapped_column(Integer, default=0)
    times_reviewed: Mapped[int] = mapped_column(Integer, default=0)
    correct_review_count: Mapped[int] = mapped_column(Integer, default=0)
    bookmarked: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VocabularyReviewSession(Base):
    __tablename__ = "vocabulary_review_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    session_id: Mapped[str] = mapped_column(String(128), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    requested_limit: Mapped[int] = mapped_column(Integer, default=10)
    due_count: Mapped[int] = mapped_column(Integer, default=0)
    reviewed_count: Mapped[int] = mapped_column(Integer, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VocabularyReviewSessionItem(Base):
    __tablename__ = "vocabulary_review_session_items"
    __table_args__ = (
        UniqueConstraint("review_session_id", "entry_id", name="uq_vocabulary_review_session_item"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    review_session_id: Mapped[int] = mapped_column(ForeignKey("vocabulary_review_sessions.id"), index=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("vocabulary_notebook_entries.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    recall_quality: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
