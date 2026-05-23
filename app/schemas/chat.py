from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str = Field(..., min_length=1, description="Unique user session id")
    message: str = Field(..., min_length=1, description="User input message")
    user_id: int | None = Field(default=None, description="Optional known user id")
    conversation_id: int | None = Field(default=None, description="Optional known conversation id")
    practice_mode: str = Field(default="chat", description="chat, voice, challenge, vocabulary, hausa, or scenario")


class EnglishLearningFeedback(BaseModel):
    correction: str
    explanation: str
    reply: str
    suggested_topic: str
    vocabulary: str = ""
    confidence_tip: str = ""


class CoachingMetricsResponse(BaseModel):
    fluency_score: int
    vocabulary_suggestions: list[str]
    daily_challenge: str
    speaking_prompt: str
    mistake_summary: str


class ChatResponse(BaseModel):
    session_id: str
    user_id: int
    conversation_id: int
    status: str
    practice_mode: str
    user_message: str
    grammar_mistakes_detected: bool
    detected_mistakes: list[str]
    correction: str
    explanation: str
    reply: str
    suggested_topic: str
    vocabulary: str
    confidence_tip: str
    assistant_message: str
    user_message_id: int
    assistant_message_id: int
    fluency_score: int
    vocabulary_suggestions: list[str]
    daily_challenge: str
    speaking_prompt: str
    mistake_summary: str
    coaching_context: dict[str, Any]
    request_id: str | None = None
    created_at: datetime


class ConversationHistoryMessage(BaseModel):
    id: int
    role: str
    content: str
    user_id: int | None
    metadata: dict[str, Any] | None = None
    created_at: datetime | None = None


class ConversationHistoryResponse(BaseModel):
    session_id: str
    user_id: int
    conversation_id: int
    title: str
    status: str
    messages: list[ConversationHistoryMessage]
    coaching_context: dict[str, Any]
    limit: int
    offset: int
    count: int
