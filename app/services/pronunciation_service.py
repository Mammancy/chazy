from __future__ import annotations

import base64
import binascii
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.pronunciation import (
    PronunciationExercise,
    PronunciationPracticeAttempt,
    PronunciationPracticeSession,
)
from app.schemas.pronunciation import (
    PronunciationAudioUploadCreate,
    PronunciationAudioUploadResponse,
    PronunciationAttemptCreate,
    PronunciationAttemptResponse,
    PronunciationExerciseResponse,
    PronunciationProgressResponse,
    PronunciationSessionCreate,
    PronunciationSessionResponse,
)

MAX_AUDIO_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_AUDIO_TYPES = {
    "audio/webm": ".webm",
    "audio/mp4": ".m4a",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/ogg": ".ogg",
}


DEFAULT_EXERCISES = [
    {
        "word": "thought",
        "phonetic_spelling": "thawt",
        "difficulty": "beginner",
        "example_sentences": ["I thought about your question.", "That was a thoughtful answer."],
        "pronunciation_tips": ["Place your tongue lightly between your teeth for th.", "Keep the vowel long and open."],
    },
    {
        "word": "world",
        "phonetic_spelling": "wurld",
        "difficulty": "beginner",
        "example_sentences": ["English is spoken around the world.", "She wants to travel the world."],
        "pronunciation_tips": ["Start with a rounded w sound.", "Hold the r before closing into ld."],
    },
    {
        "word": "comfortable",
        "phonetic_spelling": "kuhmf-ter-buhl",
        "difficulty": "intermediate",
        "example_sentences": ["This chair is comfortable.", "I feel comfortable speaking English."],
        "pronunciation_tips": ["Use three clear beats: kuhmf-ter-buhl.", "Do not over-pronounce the middle vowel."],
    },
    {
        "word": "schedule",
        "phonetic_spelling": "skeh-jool",
        "difficulty": "intermediate",
        "example_sentences": ["What is your schedule today?", "We need to schedule a meeting."],
        "pronunciation_tips": ["Use sk at the beginning for American English.", "Keep the final syllable smooth: jool."],
    },
    {
        "word": "entrepreneur",
        "phonetic_spelling": "ahn-truh-pruh-nur",
        "difficulty": "advanced",
        "example_sentences": ["She is a successful entrepreneur.", "An entrepreneur solves real problems."],
        "pronunciation_tips": ["Break it into four beats before speaking quickly.", "Keep the final r controlled and short."],
    },
]


class PronunciationService:
    def __init__(self, db: Session):
        self.db = db

    def seed_default_exercises(self) -> None:
        existing_words = {
            row[0]
            for row in self.db.query(PronunciationExercise.word).filter(
                PronunciationExercise.word.in_([item["word"] for item in DEFAULT_EXERCISES])
            )
        }
        for item in DEFAULT_EXERCISES:
            if item["word"] in existing_words:
                continue
            self.db.add(PronunciationExercise(**item))
        self.db.commit()

    def list_exercises(self, difficulty: str | None = None, limit: int = 20) -> list[PronunciationExerciseResponse]:
        query = self.db.query(PronunciationExercise).order_by(PronunciationExercise.difficulty, PronunciationExercise.word)
        if difficulty:
            query = query.filter(PronunciationExercise.difficulty == difficulty)
        return [PronunciationExerciseResponse.model_validate(row) for row in query.limit(limit).all()]

    def create_session(self, payload: PronunciationSessionCreate) -> PronunciationSessionResponse:
        exercises = self._resolve_exercises(payload)
        if not exercises:
            raise ValueError("No pronunciation words found for this request.")
        practice_session = PronunciationPracticeSession(
            client_session_id=payload.session_id,
            user_id=payload.user_id,
            target_word_count=len(exercises),
        )
        self.db.add(practice_session)
        self.db.commit()
        self.db.refresh(practice_session)
        return self._session_response(practice_session, exercises)

    def record_attempt(
        self,
        practice_session_id: int,
        payload: PronunciationAttemptCreate,
        user_id: int | None = None,
    ) -> PronunciationAttemptResponse:
        practice_session = self.db.get(PronunciationPracticeSession, practice_session_id)
        if practice_session is None:
            raise ValueError("Pronunciation practice session not found.")
        if user_id is not None and practice_session.user_id != user_id:
            raise PermissionError("Not authorized for this pronunciation session.")

        exercise = self.db.get(PronunciationExercise, payload.exercise_id)
        if exercise is None:
            raise ValueError("Pronunciation exercise not found.")

        attempt = PronunciationPracticeAttempt(
            practice_session_id=practice_session.id,
            exercise_id=exercise.id,
            user_id=practice_session.user_id,
            recorded_audio_url=payload.recorded_audio_url,
            duration_ms=payload.duration_ms,
            notes=payload.notes,
            scoring_status="not_scored",
        )
        self.db.add(attempt)

        practice_session.current_word_index = min(
            practice_session.current_word_index + 1,
            max(practice_session.target_word_count, 1),
        )
        if practice_session.current_word_index >= practice_session.target_word_count:
            practice_session.status = "completed"
            practice_session.completed_at = datetime.now(timezone.utc)

        self.db.commit()
        self.db.refresh(attempt)

        return PronunciationAttemptResponse(
            attempt_id=attempt.id,
            practice_session_id=attempt.practice_session_id,
            exercise_id=attempt.exercise_id,
            scoring_status=attempt.scoring_status,
            score=attempt.score,
            feedback=attempt.feedback,
            progress=self.get_progress(practice_session.client_session_id, practice_session.user_id),
            created_at=attempt.created_at,
        )

    def save_audio_upload(
        self,
        payload: PronunciationAudioUploadCreate,
        *,
        user_id: int,
    ) -> PronunciationAudioUploadResponse:
        content_type = payload.content_type.split(";")[0].strip().lower()
        extension = ALLOWED_AUDIO_TYPES.get(content_type)
        if extension is None:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Unsupported audio format.",
            )

        try:
            audio_bytes = base64.b64decode(self._strip_data_url(payload.data_base64), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid audio payload.",
            ) from exc

        if not audio_bytes:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Audio payload is empty.",
            )
        if len(audio_bytes) > MAX_AUDIO_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Audio recording is too large.",
            )

        upload_dir = Path(__file__).resolve().parents[1] / "static" / "uploads" / "pronunciation"
        upload_dir.mkdir(parents=True, exist_ok=True)
        safe_stem = self._safe_filename_stem(payload.filename) or "recording"
        filename = f"user-{user_id}-{safe_stem}-{uuid4().hex}{extension}"
        file_path = upload_dir / filename
        file_path.write_bytes(audio_bytes)

        return PronunciationAudioUploadResponse(
            audio_url=f"/static/uploads/pronunciation/{filename}",
            content_type=content_type,
            size_bytes=len(audio_bytes),
            duration_ms=payload.duration_ms,
        )

    def get_progress(self, session_id: str, user_id: int | None = None) -> PronunciationProgressResponse:
        session_query = self.db.query(PronunciationPracticeSession).filter(
            PronunciationPracticeSession.client_session_id == session_id
        )
        if user_id is not None:
            session_query = session_query.filter(PronunciationPracticeSession.user_id == user_id)
        sessions = session_query.order_by(PronunciationPracticeSession.created_at.desc()).all()
        session_ids = [row.id for row in sessions]

        attempts_count = 0
        words_practiced = 0
        last_practiced_at = None
        if session_ids:
            attempts_count = self.db.query(PronunciationPracticeAttempt).filter(
                PronunciationPracticeAttempt.practice_session_id.in_(session_ids)
            ).count()
            words_practiced = self.db.query(PronunciationPracticeAttempt.exercise_id).filter(
                PronunciationPracticeAttempt.practice_session_id.in_(session_ids)
            ).distinct().count()
            last_practiced_at = self.db.query(func.max(PronunciationPracticeAttempt.created_at)).filter(
                PronunciationPracticeAttempt.practice_session_id.in_(session_ids)
            ).scalar()

        active_session = sessions[0] if sessions else None
        completed_sessions = sum(1 for row in sessions if row.status == "completed")
        return PronunciationProgressResponse(
            session_id=session_id,
            user_id=user_id,
            active_session_id=active_session.id if active_session else None,
            active_status=active_session.status if active_session else None,
            words_practiced=words_practiced,
            attempts_count=attempts_count,
            completed_sessions=completed_sessions,
            last_practiced_at=last_practiced_at,
            scoring_ready=False,
        )

    def _resolve_exercises(self, payload: PronunciationSessionCreate) -> list[PronunciationExercise]:
        query = self.db.query(PronunciationExercise)
        if payload.exercise_ids:
            query = query.filter(PronunciationExercise.id.in_(payload.exercise_ids))
        elif payload.difficulty:
            query = query.filter(PronunciationExercise.difficulty == payload.difficulty)
        return query.order_by(PronunciationExercise.id).limit(payload.limit).all()

    @staticmethod
    def _strip_data_url(value: str) -> str:
        if "," in value and value.lstrip().startswith("data:"):
            return value.split(",", 1)[1]
        return value

    @staticmethod
    def _safe_filename_stem(filename: str | None) -> str:
        if not filename:
            return ""
        stem = Path(filename).stem.lower()
        return re.sub(r"[^a-z0-9_-]+", "-", stem).strip("-")[:48]

    def _session_response(
        self,
        practice_session: PronunciationPracticeSession,
        exercises: list[PronunciationExercise],
    ) -> PronunciationSessionResponse:
        return PronunciationSessionResponse(
            practice_session_id=practice_session.id,
            session_id=practice_session.client_session_id,
            user_id=practice_session.user_id,
            status=practice_session.status,
            current_word_index=practice_session.current_word_index,
            target_word_count=practice_session.target_word_count,
            exercises=[PronunciationExerciseResponse.model_validate(row) for row in exercises],
            created_at=practice_session.created_at,
        )
