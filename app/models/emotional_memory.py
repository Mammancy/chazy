from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class EmotionalMemory(Base):
    __tablename__ = "emotional_memories"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    conversation_id: Mapped[int | None] = mapped_column(
        ForeignKey("conversations.id"),
        nullable=True,
        index=True,
    )
    message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id"),
        nullable=True,
        index=True,
    )
    emotion: Mapped[str] = mapped_column(String(64), index=True)
    intensity: Mapped[float] = mapped_column(Float, default=0.5)
    trigger_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped["User"] = relationship(back_populates="emotional_memories")
    conversation: Mapped["Conversation | None"] = relationship(back_populates="emotional_memories")
    message: Mapped["Message | None"] = relationship(back_populates="emotional_memories")

