from datetime import date, datetime

from pydantic import BaseModel, Field


class VocabularyEntryCreate(BaseModel):
    session_id: str = Field(..., min_length=1)
    user_id: int | None = Field(default=None, ge=1)
    word: str = Field(..., min_length=1, max_length=120)
    meaning: str = Field(..., min_length=1)
    example_sentence: str = Field(..., min_length=1)
    mastery_status: str = Field(default="new")
    review_date: date | None = None
    source_message_id: int | None = Field(default=None, ge=1)
    bookmarked: bool = True
    notes: str | None = None


class VocabularyBookmarkFromConversationRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    user_id: int | None = Field(default=None, ge=1)
    message_id: int = Field(..., ge=1)
    word: str = Field(..., min_length=1, max_length=120)
    meaning: str | None = None
    example_sentence: str | None = None


class VocabularyEntryUpdate(BaseModel):
    meaning: str | None = None
    example_sentence: str | None = None
    mastery_status: str | None = None
    review_date: date | None = None
    bookmarked: bool | None = None
    notes: str | None = None


class VocabularyReviewRequest(BaseModel):
    correct: bool = True
    recall_quality: int | None = Field(default=None, ge=0, le=5)
    next_review_date: date | None = None
    mastery_status: str | None = None


class VocabularyEntryResponse(BaseModel):
    id: int
    session_id: str
    user_id: int | None
    source_message_id: int | None
    word: str
    meaning: str
    example_sentence: str
    mastery_status: str
    review_date: date | None
    retention_score: float
    ease_factor: float
    review_interval_days: int
    consecutive_correct: int
    times_reviewed: int
    correct_review_count: int
    bookmarked: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime
    last_reviewed_at: datetime | None

    model_config = {"from_attributes": True}


class VocabularyNotebookStatsResponse(BaseModel):
    session_id: str
    user_id: int | None
    total_words: int
    bookmarked_words: int
    new_words: int
    learning_words: int
    mastered_words: int
    due_for_review: int
    total_reviews: int
    review_accuracy_percent: int
    average_retention_score: int
    active_review_sessions: int


class VocabularyNotebookResponse(BaseModel):
    session_id: str
    user_id: int | None
    entries: list[VocabularyEntryResponse]
    stats: VocabularyNotebookStatsResponse


class VocabularyReviewSessionCreate(BaseModel):
    session_id: str = Field(..., min_length=1)
    user_id: int | None = Field(default=None, ge=1)
    limit: int = Field(default=10, ge=1, le=50)
    include_new: bool = True


class VocabularyReviewSessionItemResponse(BaseModel):
    id: int
    entry_id: int
    status: str
    recall_quality: int | None
    reviewed_at: datetime | None
    entry: VocabularyEntryResponse


class VocabularyReviewSessionResponse(BaseModel):
    review_session_id: int
    session_id: str
    user_id: int | None
    status: str
    requested_limit: int
    due_count: int
    reviewed_count: int
    correct_count: int
    accuracy_percent: int
    items: list[VocabularyReviewSessionItemResponse]
    created_at: datetime
    completed_at: datetime | None


class VocabularyReviewSessionItemSubmit(BaseModel):
    item_id: int = Field(..., ge=1)
    recall_quality: int = Field(..., ge=0, le=5)


class VocabularyReviewSessionSubmit(BaseModel):
    reviews: list[VocabularyReviewSessionItemSubmit] = Field(default_factory=list)
