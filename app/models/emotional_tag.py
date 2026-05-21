from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class EmotionalTag(Base):
    __tablename__ = "emotional_tags"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    message_links: Mapped[list["MessageEmotionalTag"]] = relationship(
        back_populates="emotional_tag",
        cascade="all, delete-orphan",
    )
    messages: Mapped[list["Message"]] = relationship(
        secondary="message_emotional_tags",
        viewonly=True,
    )


class MessageEmotionalTag(Base):
    __tablename__ = "message_emotional_tags"

    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id"), primary_key=True)
    emotional_tag_id: Mapped[int] = mapped_column(ForeignKey("emotional_tags.id"), primary_key=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    message: Mapped["Message"] = relationship(back_populates="emotional_tag_links")
    emotional_tag: Mapped["EmotionalTag"] = relationship(back_populates="message_links")
