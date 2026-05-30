from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.message import Message
from app.models.vocabulary_notebook import (
    VocabularyNotebookEntry,
    VocabularyReviewSession,
    VocabularyReviewSessionItem,
)
from app.schemas.vocabulary_notebook import (
    VocabularyBookmarkFromConversationRequest,
    VocabularyEntryCreate,
    VocabularyEntryResponse,
    VocabularyEntryUpdate,
    VocabularyNotebookResponse,
    VocabularyNotebookStatsResponse,
    VocabularyReviewRequest,
    VocabularyReviewSessionCreate,
    VocabularyReviewSessionItemResponse,
    VocabularyReviewSessionResponse,
    VocabularyReviewSessionSubmit,
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
        if payload.user_id is not None and message.user_id is not None and message.user_id != payload.user_id:
            raise PermissionError("Not authorized for this conversation message.")
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

    def update_entry(
        self,
        entry_id: int,
        payload: VocabularyEntryUpdate,
        user_id: int | None = None,
    ) -> VocabularyEntryResponse:
        entry = self.db.get(VocabularyNotebookEntry, entry_id)
        if entry is None:
            raise ValueError("Vocabulary entry not found.")
        self._authorize_entry(entry, user_id)
        self._apply_entry_update(entry, payload)
        self.db.commit()
        self.db.refresh(entry)
        return VocabularyEntryResponse.model_validate(entry)

    def record_review(
        self,
        entry_id: int,
        payload: VocabularyReviewRequest,
        user_id: int | None = None,
    ) -> VocabularyEntryResponse:
        entry = self.db.get(VocabularyNotebookEntry, entry_id)
        if entry is None:
            raise ValueError("Vocabulary entry not found.")
        self._authorize_entry(entry, user_id)
        recall_quality = payload.recall_quality if payload.recall_quality is not None else (5 if payload.correct else 2)
        self._apply_spaced_repetition(entry, recall_quality, payload.next_review_date, payload.mastery_status)
        self.db.commit()
        self.db.refresh(entry)
        return VocabularyEntryResponse.model_validate(entry)

    def delete_entry(self, entry_id: int, user_id: int | None = None) -> None:
        entry = self.db.get(VocabularyNotebookEntry, entry_id)
        if entry is None:
            raise ValueError("Vocabulary entry not found.")
        self._authorize_entry(entry, user_id)
        review_items = list(
            self.db.scalars(
                select(VocabularyReviewSessionItem).where(
                    VocabularyReviewSessionItem.entry_id == entry.id
                )
            ).all()
        )
        for item in review_items:
            self.db.delete(item)
        self.db.delete(entry)
        self.db.commit()

    def create_review_session(self, payload: VocabularyReviewSessionCreate) -> VocabularyReviewSessionResponse:
        entries = self._due_entries(
            session_id=payload.session_id,
            user_id=payload.user_id,
            limit=payload.limit,
            include_new=payload.include_new,
        )
        review_session = VocabularyReviewSession(
            session_id=payload.session_id,
            user_id=payload.user_id,
            requested_limit=payload.limit,
            due_count=len(entries),
        )
        self.db.add(review_session)
        self.db.flush()
        for entry in entries:
            self.db.add(VocabularyReviewSessionItem(review_session_id=review_session.id, entry_id=entry.id))
        self.db.commit()
        self.db.refresh(review_session)
        return self.get_review_session(review_session.id, user_id=payload.user_id)

    def get_review_session(
        self,
        review_session_id: int,
        user_id: int | None = None,
    ) -> VocabularyReviewSessionResponse:
        review_session = self.db.get(VocabularyReviewSession, review_session_id)
        if review_session is None:
            raise ValueError("Vocabulary review session not found.")
        self._authorize_review_session(review_session, user_id)
        items = self._review_session_items(review_session.id)
        return self._review_session_response(review_session, items)

    def submit_review_session(
        self,
        review_session_id: int,
        payload: VocabularyReviewSessionSubmit,
        user_id: int | None = None,
    ) -> VocabularyReviewSessionResponse:
        review_session = self.db.get(VocabularyReviewSession, review_session_id)
        if review_session is None:
            raise ValueError("Vocabulary review session not found.")
        self._authorize_review_session(review_session, user_id)
        item_by_id = {item.id: item for item in self._review_session_items(review_session.id)}
        for review in payload.reviews:
            item = item_by_id.get(review.item_id)
            if item is None:
                raise ValueError("Vocabulary review session item not found.")
            entry = self.db.get(VocabularyNotebookEntry, item.entry_id)
            if entry is None:
                continue
            self._apply_spaced_repetition(entry, review.recall_quality, None, None)
            item.status = "reviewed"
            item.recall_quality = review.recall_quality
            item.reviewed_at = datetime.now(timezone.utc)

        reviewed_items = [item for item in item_by_id.values() if item.status == "reviewed"]
        review_session.reviewed_count = len(reviewed_items)
        review_session.correct_count = sum(1 for item in reviewed_items if (item.recall_quality or 0) >= 3)
        if review_session.reviewed_count >= review_session.due_count:
            review_session.status = "completed"
            review_session.completed_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(review_session)
        return self.get_review_session(review_session.id, user_id=user_id)

    def _apply_spaced_repetition(
        self,
        entry: VocabularyNotebookEntry,
        recall_quality: int,
        next_review_date,
        mastery_status: str | None,
    ) -> None:
        entry.times_reviewed += 1
        correct = recall_quality >= 3
        if correct:
            entry.correct_review_count += 1
            entry.consecutive_correct += 1
        else:
            entry.consecutive_correct = 0
        entry.last_reviewed_at = datetime.now(timezone.utc)
        entry.ease_factor = self._next_ease_factor(entry.ease_factor, recall_quality)
        entry.review_interval_days = self._next_interval(entry, recall_quality)
        entry.retention_score = self._next_retention_score(entry, recall_quality)
        if mastery_status:
            entry.mastery_status = mastery_status
        elif entry.consecutive_correct >= 4 and entry.retention_score >= 80:
            entry.mastery_status = "mastered"
        elif entry.times_reviewed >= 1:
            entry.mastery_status = "learning"
        elif entry.mastery_status == "new":
            entry.mastery_status = "learning"
        entry.review_date = next_review_date or date.today() + timedelta(days=entry.review_interval_days)

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
            average_retention_score=round(sum(entry.retention_score for entry in entries) / len(entries)) if entries else 0,
            active_review_sessions=self.db.query(VocabularyReviewSession).filter(
                VocabularyReviewSession.session_id == session_id,
                VocabularyReviewSession.status == "active",
            ).count(),
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

    @staticmethod
    def _authorize_entry(entry: VocabularyNotebookEntry, user_id: int | None) -> None:
        if user_id is not None and entry.user_id != user_id:
            raise PermissionError("Not authorized for this vocabulary entry.")

    @staticmethod
    def _authorize_review_session(review_session: VocabularyReviewSession, user_id: int | None) -> None:
        if user_id is not None and review_session.user_id != user_id:
            raise PermissionError("Not authorized for this vocabulary review session.")

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

    def _due_entries(
        self,
        *,
        session_id: str,
        user_id: int | None,
        limit: int,
        include_new: bool,
    ) -> list[VocabularyNotebookEntry]:
        query = select(VocabularyNotebookEntry).where(VocabularyNotebookEntry.session_id == session_id)
        if user_id is not None:
            query = query.where(VocabularyNotebookEntry.user_id == user_id)
        if include_new:
            query = query.where(
                (VocabularyNotebookEntry.review_date <= date.today())
                | (VocabularyNotebookEntry.review_date.is_(None))
                | (VocabularyNotebookEntry.mastery_status == "new")
            )
        else:
            query = query.where(VocabularyNotebookEntry.review_date <= date.today())
        return list(
            self.db.scalars(
                query.order_by(
                    VocabularyNotebookEntry.review_date.asc(),
                    VocabularyNotebookEntry.retention_score.asc(),
                    VocabularyNotebookEntry.updated_at.asc(),
                ).limit(limit)
            ).all()
        )

    def _review_session_items(self, review_session_id: int) -> list[VocabularyReviewSessionItem]:
        return list(
            self.db.scalars(
                select(VocabularyReviewSessionItem)
                .where(VocabularyReviewSessionItem.review_session_id == review_session_id)
                .order_by(VocabularyReviewSessionItem.id.asc())
            ).all()
        )

    def _review_session_response(
        self,
        review_session: VocabularyReviewSession,
        items: list[VocabularyReviewSessionItem],
    ) -> VocabularyReviewSessionResponse:
        item_responses = []
        for item in items:
            entry = self.db.get(VocabularyNotebookEntry, item.entry_id)
            if entry is None:
                continue
            item_responses.append(
                VocabularyReviewSessionItemResponse(
                    id=item.id,
                    entry_id=item.entry_id,
                    status=item.status,
                    recall_quality=item.recall_quality,
                    reviewed_at=item.reviewed_at,
                    entry=VocabularyEntryResponse.model_validate(entry),
                )
            )
        accuracy = round((review_session.correct_count / review_session.reviewed_count) * 100) if review_session.reviewed_count else 0
        return VocabularyReviewSessionResponse(
            review_session_id=review_session.id,
            session_id=review_session.session_id,
            user_id=review_session.user_id,
            status=review_session.status,
            requested_limit=review_session.requested_limit,
            due_count=review_session.due_count,
            reviewed_count=review_session.reviewed_count,
            correct_count=review_session.correct_count,
            accuracy_percent=accuracy,
            items=item_responses,
            created_at=review_session.created_at,
            completed_at=review_session.completed_at,
        )

    def _next_ease_factor(self, current: float, recall_quality: int) -> float:
        quality = max(0, min(5, recall_quality))
        adjusted = current + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        return max(1.3, round(adjusted, 2))

    def _next_interval(self, entry: VocabularyNotebookEntry, recall_quality: int) -> int:
        if recall_quality < 3:
            return 1
        if entry.times_reviewed <= 1:
            return 1
        if entry.times_reviewed == 2:
            return 3
        return max(4, round(entry.review_interval_days * entry.ease_factor))

    def _next_retention_score(self, entry: VocabularyNotebookEntry, recall_quality: int) -> float:
        quality_score = (max(0, min(5, recall_quality)) / 5) * 100
        if entry.times_reviewed <= 1:
            return round(quality_score, 1)
        return round((entry.retention_score * 0.7) + (quality_score * 0.3), 1)

    def _normalize_word(self, word: str) -> str:
        return " ".join(word.strip().lower().split())
