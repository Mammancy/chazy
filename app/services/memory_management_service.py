from __future__ import annotations

from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.memory.session_memory import SessionMemoryStore
from app.models.memory import Memory
from app.models.memory_summary import MemorySummary
from app.models.message import Message

DEFAULT_MEMORY_CACHE = SessionMemoryStore()


class MemoryManagementService:
    """Stores conversation history and learning-focused user details."""

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
        metadata: dict[str, Any] | None = None,
    ) -> Message:
        message = Message(
            conversation_id=conversation_id,
            user_id=user_id,
            role=role,
            content=content,
            metadata_json=metadata or {},
        )
        self.db.add(message)
        self._flush_refresh(message)

        if user_id is not None:
            history_memory = Memory(
                user_id=user_id,
                conversation_id=conversation_id,
                key="conversation_history",
                value=content,
                salience_score=0.25,
                metadata_json={**(metadata or {}), "message_id": message.id, "role": role},
            )
            self.db.add(history_memory)
            self._flush_refresh(history_memory)
            self.cache.add(f"conversation:{conversation_id}:history", f"{role}: {content}")
        return message

    def store_user_detail(
        self,
        *,
        user_id: int,
        detail_key: str,
        detail_value: str,
        conversation_id: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Memory:
        key = f"user_detail:{detail_key.strip().lower()}"
        existing = self.db.scalar(
            select(Memory)
            .where(Memory.user_id == user_id, Memory.key == key)
            .order_by(desc(Memory.updated_at))
            .limit(1)
        )
        if existing is not None:
            memory = existing
            memory.value = detail_value
            memory.metadata_json = {**(memory.metadata_json or {}), **(metadata or {})}
            memory.salience_score = max(memory.salience_score or 0.0, 0.75)
        else:
            memory = Memory(
                user_id=user_id,
                conversation_id=conversation_id,
                key=key,
                value=detail_value,
                salience_score=0.75,
                metadata_json=metadata or {},
            )
            self.db.add(memory)
        self._flush_refresh(memory)
        self.cache.add(f"user:{user_id}:details", f"{detail_key}:{detail_value}")
        return memory

    def store_memory_summary(
        self,
        *,
        user_id: int,
        summary: str,
        conversation_id: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemorySummary:
        memory_summary = MemorySummary(
            user_id=user_id,
            conversation_id=conversation_id,
            summary=summary,
            summary_type="learning_progress",
            metadata_json=metadata or {},
        )
        self.db.add(memory_summary)
        self._flush_refresh(memory_summary)
        memory = Memory(
            user_id=user_id,
            conversation_id=conversation_id,
            key="learning_summary",
            value=summary,
            salience_score=0.5,
            metadata_json={**(metadata or {}), "memory_summary_id": memory_summary.id},
        )
        self.db.add(memory)
        self._flush_refresh(memory)
        self.cache.add(f"user:{user_id}:summaries", summary)
        return memory_summary

    def get_important_user_details(self, *, user_id: int, limit: int = 50) -> list[Memory]:
        return list(
            self.db.scalars(
                select(Memory)
                .where(Memory.user_id == user_id, Memory.key.like("user_detail:%"))
                .order_by(desc(Memory.salience_score), desc(Memory.updated_at), desc(Memory.id))
                .limit(limit)
            ).all()
        )

    def get_learning_summaries(self, *, user_id: int, limit: int = 20) -> list[MemorySummary]:
        return list(
            self.db.scalars(
                select(MemorySummary)
                .where(MemorySummary.user_id == user_id)
                .order_by(desc(MemorySummary.updated_at), desc(MemorySummary.id))
                .limit(limit)
            ).all()
        )

    def build_learning_snapshot(self, *, user_id: int, detail_limit: int = 20, summary_limit: int = 10) -> dict[str, Any]:
        return {
            "important_user_details": [
                {"key": item.key.replace("user_detail:", "", 1), "value": item.value, "score": item.salience_score}
                for item in self.get_important_user_details(user_id=user_id, limit=detail_limit)
            ],
            "learning_summaries": [
                {"summary": item.summary, "type": item.summary_type, "updated_at": item.updated_at}
                for item in self.get_learning_summaries(user_id=user_id, limit=summary_limit)
            ],
        }

    def _flush_refresh(self, instance: Any) -> None:
        self.db.commit()
        self.db.refresh(instance)
