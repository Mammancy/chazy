from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, JSON, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class MemorySummary(Base):
    __tablename__ = "memory_summaries"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    conversation_id: Mapped[int | None] = mapped_column(
        ForeignKey("conversations.id"),
        nullable=True,
        index=True,
    )
    summary: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    salience_score: Mapped[float] = mapped_column(Float, default=0.9)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped["User"] = relationship(back_populates="memory_summaries")
    conversation: Mapped["Conversation | None"] = relationship(back_populates="memory_summaries")
