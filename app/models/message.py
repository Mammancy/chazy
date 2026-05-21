from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(32), index=True)
    content: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
    user: Mapped["User | None"] = relationship(back_populates="messages")
    emotional_tag_links: Mapped[list["MessageEmotionalTag"]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
    )
    emotional_tags: Mapped[list["EmotionalTag"]] = relationship(
        secondary="message_emotional_tags",
        viewonly=True,
    )
    emotional_memories: Mapped[list["EmotionalMemory"]] = relationship(back_populates="message")
