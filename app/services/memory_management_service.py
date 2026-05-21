from __future__ import annotations

from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.memory.session_memory import SessionMemoryStore
from app.models.emotional_memory import EmotionalMemory
from app.models.emotional_tag import EmotionalTag, MessageEmotionalTag
from app.models.memory import Memory
from app.models.memory_summary import MemorySummary
from app.models.message import Message

DEFAULT_MEMORY_CACHE = SessionMemoryStore()


class MemoryManagementService:
    """Stores and retrieves ABOKI memory signals across core memory domains."""

    def __init__(self, db: Session, cache: SessionMemoryStore | None = None) -> None:
        self.db = db
        self.cache = cache or DEFAULT_MEMORY_CACHE

    def store_conversation_history(
        self,
        *,
        conversation_id: int,
        role: str,
        content: str,
        user_id: int | None = None,
        token_count: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Message:
        message = Message(
            conversation_id=conversation_id,
            user_id=user_id,
            role=role,
            content=content,
            token_count=token_count,
            metadata_json=metadata,
        )
        self.db.add(message)
        self._flush_refresh(message)

        self.cache.add(
            f"conversation:{conversation_id}",
            f"{role}:{content}",
        )

        if user_id is not None:
            history_memory = Memory(
                user_id=user_id,
                conversation_id=conversation_id,
                key="conversation_history",
                value=content,
                metadata_json={
                    "role": role,
                    "message_id": message.id,
                    "token_count": token_count,
                    **(metadata or {}),
                },
                salience_score=0.6,
            )
            self.db.add(history_memory)

        self._commit()
        return message

    def store_emotional_pattern(
        self,
        *,
        user_id: int,
        emotion: str,
        intensity: float,
        conversation_id: int | None = None,
        message_id: int | None = None,
        trigger_text: str | None = None,
        notes: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EmotionalMemory:
        emotional_memory = EmotionalMemory(
            user_id=user_id,
            conversation_id=conversation_id,
            message_id=message_id,
            emotion=emotion,
            intensity=intensity,
            trigger_text=trigger_text,
            notes=notes,
            metadata_json=metadata,
        )
        self.db.add(emotional_memory)
        self._flush_refresh(emotional_memory)

        if message_id is not None:
            emotional_tag = self._get_or_create_emotional_tag(emotion)
            existing_link = self.db.get(
                MessageEmotionalTag,
                {
                    "message_id": message_id,
                    "emotional_tag_id": emotional_tag.id,
                },
            )
            if existing_link is None:
                self.db.add(
                    MessageEmotionalTag(
                        message_id=message_id,
                        emotional_tag_id=emotional_tag.id,
                        confidence=max(0.0, min(float(intensity), 1.0)),
                    )
                )

        self.cache.add(
            f"user:{user_id}:emotions",
            f"{emotion}:{intensity}",
        )

        self._commit()
        return emotional_memory

    def store_user_detail(
        self,
        *,
        user_id: int,
        detail_key: str,
        detail_value: str,
        conversation_id: int | None = None,
        metadata: dict[str, Any] | None = None,
        salience_score: float = 0.8,
    ) -> Memory:
        key = f"user_detail:{detail_key.strip().lower()}"
        existing = self.db.scalar(
            select(Memory)
            .where(Memory.user_id == user_id, Memory.key == key)
            .order_by(desc(Memory.updated_at))
            .limit(1)
        )
        if existing:
            existing.value = detail_value
            existing.conversation_id = conversation_id
            existing.metadata_json = metadata
            existing.salience_score = salience_score
            memory = existing
        else:
            memory = Memory(
                user_id=user_id,
                conversation_id=conversation_id,
                key=key,
                value=detail_value,
                metadata_json=metadata,
                salience_score=salience_score,
            )
            self.db.add(memory)

        self._flush_refresh(memory)
        self.cache.add(f"user:{user_id}:details", f"{detail_key}:{detail_value}")
        self._commit()
        return memory

    def store_memory_summary(
        self,
        *,
        user_id: int,
        summary: str,
        conversation_id: int | None = None,
        metadata: dict[str, Any] | None = None,
        salience_score: float = 0.9,
    ) -> MemorySummary:
        memory_summary = MemorySummary(
            user_id=user_id,
            conversation_id=conversation_id,
            summary=summary,
            metadata_json=metadata,
            salience_score=salience_score,
        )
        self.db.add(memory_summary)
        self._flush_refresh(memory_summary)

        # Keep a generic memory row for older snapshot queries and future search/ranking logic.
        memory = Memory(
            user_id=user_id,
            conversation_id=conversation_id,
            key="memory_summary",
            value=summary,
            metadata_json={**(metadata or {}), "memory_summary_id": memory_summary.id},
            salience_score=salience_score,
        )
        self.db.add(memory)
        self._flush_refresh(memory)

        self.cache.add(f"user:{user_id}:summaries", summary)

        self._commit()
        return memory_summary

    def get_conversation_history(self, *, conversation_id: int, limit: int = 100) -> list[Message]:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc(), Message.id.asc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def get_emotional_patterns(self, *, user_id: int, limit: int = 50) -> list[EmotionalMemory]:
        stmt = (
            select(EmotionalMemory)
            .where(EmotionalMemory.user_id == user_id)
            .order_by(desc(EmotionalMemory.created_at), desc(EmotionalMemory.id))
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def get_important_user_details(self, *, user_id: int, limit: int = 50) -> list[Memory]:
        stmt = (
            select(Memory)
            .where(Memory.user_id == user_id, Memory.key.like("user_detail:%"))
            .order_by(desc(Memory.salience_score), desc(Memory.updated_at), desc(Memory.id))
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def get_memory_summaries(self, *, user_id: int, limit: int = 20) -> list[MemorySummary]:
        stmt = (
            select(MemorySummary)
            .where(MemorySummary.user_id == user_id)
            .order_by(desc(MemorySummary.updated_at), desc(MemorySummary.id))
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def build_memory_snapshot(
        self,
        *,
        user_id: int,
        conversation_id: int | None = None,
        history_limit: int = 30,
        emotion_limit: int = 20,
        detail_limit: int = 20,
        summary_limit: int = 5,
    ) -> dict[str, Any]:
        history: list[Message] = []
        if conversation_id is not None:
            history = self.get_conversation_history(
                conversation_id=conversation_id,
                limit=history_limit,
            )

        return {
            "conversation_history": [
                {
                    "id": msg.id,
                    "role": msg.role,
                    "content": msg.content,
                    "metadata": msg.metadata_json,
                    "created_at": msg.created_at.isoformat() if msg.created_at else None,
                }
                for msg in history
            ],
            "emotional_patterns": [
                {
                    "emotion": item.emotion,
                    "intensity": item.intensity,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                }
                for item in self.get_emotional_patterns(user_id=user_id, limit=emotion_limit)
            ],
            "important_user_details": [
                {
                    "key": item.key.replace("user_detail:", "", 1),
                    "value": item.value,
                    "salience_score": item.salience_score,
                }
                for item in self.get_important_user_details(user_id=user_id, limit=detail_limit)
            ],
            "memory_summaries": [
                {
                    "summary": item.summary,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                }
                for item in self.get_memory_summaries(user_id=user_id, limit=summary_limit)
            ],
        }

    def _get_or_create_emotional_tag(self, emotion: str) -> EmotionalTag:
        normalized = emotion.strip().lower() or "neutral"
        emotional_tag = self.db.scalar(
            select(EmotionalTag)
            .where(EmotionalTag.name == normalized)
            .limit(1)
        )
        if emotional_tag is not None:
            return emotional_tag

        emotional_tag = EmotionalTag(
            name=normalized,
            description=f"Detected {normalized} emotional tone",
        )
        self.db.add(emotional_tag)
        self._flush_refresh(emotional_tag)
        return emotional_tag

    def _flush_refresh(self, instance: Any) -> None:
        self.db.flush()
        self.db.refresh(instance)

    def _commit(self) -> None:
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
