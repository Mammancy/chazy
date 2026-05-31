from datetime import datetime

from pydantic import BaseModel, Field


class PronunciationExerciseResponse(BaseModel):
    id: int
    word: str
    phonetic_spelling: str
    difficulty: str
    audio_url: str | None = None
    example_sentences: list[str]
    pronunciation_tips: list[str]

    model_config = {"from_attributes": True}


class PronunciationSessionCreate(BaseModel):
    session_id: str = Field(..., min_length=1)
    user_id: int | None = Field(default=None, ge=1)
    difficulty: str | None = Field(default=None)
    limit: int = Field(default=5, ge=1, le=20)
    exercise_ids: list[int] | None = None


class PronunciationSessionResponse(BaseModel):
    practice_session_id: int
    session_id: str
    user_id: int | None
    status: str
    current_word_index: int
    target_word_count: int
    exercises: list[PronunciationExerciseResponse]
    created_at: datetime


class PronunciationAttemptCreate(BaseModel):
    exercise_id: int = Field(..., ge=1)
    recorded_audio_url: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    notes: str | None = None


class PronunciationAudioUploadCreate(BaseModel):
    filename: str | None = Field(default=None, max_length=160)
    content_type: str = Field(default="audio/webm", max_length=80)
    data_base64: str = Field(..., min_length=1)
    duration_ms: int | None = Field(default=None, ge=0)


class PronunciationAudioUploadResponse(BaseModel):
    audio_url: str
    content_type: str
    size_bytes: int
    duration_ms: int | None = None


class PronunciationAttemptResponse(BaseModel):
    attempt_id: int
    practice_session_id: int
    exercise_id: int
    scoring_status: str
    score: int | None = None
    feedback: str | None = None
    progress: "PronunciationProgressResponse"
    created_at: datetime


class PronunciationProgressResponse(BaseModel):
    session_id: str
    user_id: int | None
    active_session_id: int | None
    active_status: str | None
    words_practiced: int
    attempts_count: int
    completed_sessions: int
    last_practiced_at: datetime | None = None
    scoring_ready: bool = False
