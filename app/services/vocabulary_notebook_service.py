from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.message import Message
from app.models.vocabulary_notebook import VocabularyNotebookEntry
from app.schemas.vocabulary_notebook import (
    VocabularyBookmarkFromConversationRequest,
    VocabularyEntryCreate,
    VocabularyEntryResponse,
    VocabularyEntryUpdate,
    VocabularyNotebookResponse,
    VocabularyNotebookStatsResponse,
    VocabularyReviewRequest,
)


class VocabularyNotebookService:
    def __init__(self, db: Session):
        self.db = db

    def list_entries(
        self,
        *,
        session_id: str,
        user_id: int | None = None,
        mastery_status: str | None = None,
        bookmarked: bool | None = None,
        due_only: bool = False,
    ) -> VocabularyNotebookResponse:
        entries = list(
            self.db.scalars(
                self._base_query(session_id, user_id, mastery_status, bookmarked, due_only)
                .order_by(VocabularyNotebookEntry.updated_at.desc(), VocabularyNotebookEntry.word.asc())
            ).all()
        )
        return VocabularyNotebookResponse(
            session_id=session_id,
            user_id=user_id,
            entries=[VocabularyEntryResponse.model_validate(entry) for entry in entries],
            stats=self.stats(session_id=session_id, user_id=user_id),
        )

    def create_entry(self, payload: VocabularyEntryCreate) -> VocabularyEntryResponse:
        entry = VocabularyNotebookEntry(
            session_id=payload.session_id,
            user_id=payload.user_id,
            source_message_id=payload.source_message_id,
            word=self._normalize_word(payload.word),
            meaning=payload.meaning.strip(),
            example_sentence=payload.example_sentence.strip(),
            mastery_status=payload.mastery_status,
            review_date=payload.review_date or date.today() + timedelta(days=1),
            bookmarked=payload.bookmarked,
            notes=payload.notes,
        )
        self.db.add(entry)
        try:
            self.db.commit()
            self.db.refresh(entry)
        except IntegrityError:
            self.db.rollback()
            entry = self._existing(payload.session_id, payload.user_id, payload.word)
            if entry is None:
                raise
            self._apply_entry_update(
                entry,
                VocabularyEntryUpdate(
                    meaning=payload.meaning,
                    example_sentence=payload.example_sentence,
                    mastery_status=payload.mastery_status,
                    review_date=payload.review_date,
                    bookmarked=payload.bookmarked,
                    notes=payload.notes,
                ),
            )
            if payload.source_message_id is not None:
                entry.source_message_id = payload.source_message_id
            self.db.commit()
            self.db.refresh(entry)
        return VocabularyEntryResponse.model_validate(entry)

    def bookmark_from_conversation(self, payload: VocabularyBookmarkFromConversationRequest) -> VocabularyEntryResponse:
        message = self.db.get(Message, payload.message_id)
        if message is None:
            raise ValueError("Conversation message not found.")
        example = payload.example_sentence or self._sentence_for_word(message.content, payload.word)
        meaning = payload.meaning or self._meaning_from_message_metadata(message, payload.word)
        return self.create_entry(
            VocabularyEntryCreate(
                session_id=payload.session_id,
                user_id=payload.user_id or message.user_id,
                source_message_id=message.id,
                word=payload.word,
                meaning=meaning,
                example_sentence=example,
                bookmarked=True,
            )
        )

    def update_entry(self, entry_id: int, payload: VocabularyEntryUpdate) -> VocabularyEntryResponse:
        entry = self.db.get(VocabularyNotebookEntry, entry_id)
        if entry is None:
            raise ValueError("Vocabulary entry not found.")
        self._apply_entry_update(entry, payload)
        self.db.commit()
        self.db.refresh(entry)
        return VocabularyEntryResponse.model_validate(entry)

    def record_review(self, entry_id: int, payload: VocabularyReviewRequest) -> VocabularyEntryResponse:
        entry = self.db.get(VocabularyNotebookEntry, entry_id)
        if entry is None:
            raise ValueError("Vocabulary entry not found.")
        entry.times_reviewed += 1
        if payload.correct:
            entry.correct_review_count += 1
        entry.last_reviewed_at = datetime.now(timezone.utc)
        if payload.mastery_status:
            entry.mastery_status = payload.mastery_status
        elif payload.correct and entry.times_reviewed >= 3:
            entry.mastery_status = "mastered"
        elif entry.mastery_status == "new":
            entry.mastery_status = "learning"
        entry.review_date = payload.next_review_date or self._next_review_date(entry, payload.correct)
        self.db.commit()
        self.db.refresh(entry)
        return VocabularyEntryResponse.model_validate(entry)

    def stats(self, *, session_id: str, user_id: int | None = None) -> VocabularyNotebookStatsResponse:
        entries = list(self.db.scalars(self._base_query(session_id, user_id, None, None, False)).all())
        total_reviews = sum(entry.times_reviewed for entry in entries)
        correct_reviews = sum(entry.correct_review_count for entry in entries)
        return VocabularyNotebookStatsResponse(
            session_id=session_id,
            user_id=user_id,
            total_words=len(entries),
            bookmarked_words=sum(1 for entry in entries if entry.bookmarked),
            new_words=sum(1 for entry in entries if entry.mastery_status == "new"),
            learning_words=sum(1 for entry in entries if entry.mastery_status == "learning"),
            mastered_words=sum(1 for entry in entries if entry.mastery_status == "mastered"),
            due_for_review=sum(1 for entry in entries if entry.review_date is not None and entry.review_date <= date.today()),
            total_reviews=total_reviews,
            review_accuracy_percent=round((correct_reviews / total_reviews) * 100) if total_reviews else 0,
        )

    def _base_query(
        self,
        session_id: str,
        user_id: int | None,
        mastery_status: str | None,
        bookmarked: bool | None,
        due_only: bool,
    ):
        query = select(VocabularyNotebookEntry).where(VocabularyNotebookEntry.session_id == session_id)
        if user_id is not None:
            query = query.where(VocabularyNotebookEntry.user_id == user_id)
        if mastery_status:
            query = query.where(VocabularyNotebookEntry.mastery_status == mastery_status)
        if bookmarked is not None:
            query = query.where(VocabularyNotebookEntry.bookmarked == bookmarked)
        if due_only:
            query = query.where(VocabularyNotebookEntry.review_date <= date.today())
        return query

    def _existing(self, session_id: str, user_id: int | None, word: str) -> VocabularyNotebookEntry | None:
        return self.db.scalar(
            select(VocabularyNotebookEntry).where(
                VocabularyNotebookEntry.session_id == session_id,
                VocabularyNotebookEntry.user_id == user_id,
                VocabularyNotebookEntry.word == self._normalize_word(word),
            ).limit(1)
        )

    def _apply_entry_update(self, entry: VocabularyNotebookEntry, payload: VocabularyEntryUpdate) -> None:
        for field in ("meaning", "example_sentence", "mastery_status", "review_date", "bookmarked", "notes"):
            value = getattr(payload, field)
            if value is not None:
                setattr(entry, field, value.strip() if isinstance(value, str) else value)

    def _sentence_for_word(self, text: str, word: str) -> str:
        clean_word = self._normalize_word(word)
        sentences = [sentence.strip() for sentence in text.replace("?", ".").replace("!", ".").split(".")]
        for sentence in sentences:
            if clean_word in sentence.lower().split():
                return sentence + "."
        return text.strip()[:240] or f"I learned the word {clean_word}."

    def _meaning_from_message_metadata(self, message: Message, word: str) -> str:
        metadata = message.metadata_json or {}
        suggestions = metadata.get("vocabulary_suggestions") or []
        clean_word = self._normalize_word(word)
        for suggestion in suggestions:
            if isinstance(suggestion, str) and clean_word in suggestion.lower():
                return suggestion
        return f"Meaning for {clean_word}. Add your own definition after review."

    def _next_review_date(self, entry: VocabularyNotebookEntry, correct: bool) -> date:
        if not correct:
            return date.today() + timedelta(days=1)
        if entry.mastery_status == "mastered":
            return date.today() + timedelta(days=14)
        if entry.times_reviewed >= 3:
            return date.today() + timedelta(days=7)
        return date.today() + timedelta(days=3)

    def _normalize_word(self, word: str) -> str:
        return " ".join(word.strip().lower().split())
