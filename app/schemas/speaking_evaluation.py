from datetime import datetime

from pydantic import BaseModel, Field


class SpeakingCorrection(BaseModel):
    original: str
    corrected: str


class SpeakingEvaluationRequest(BaseModel):
    transcript: str = Field(..., min_length=1, max_length=5000)
    duration_seconds: int = Field(..., ge=1, le=1800)


class SpeakingEvaluationResponse(BaseModel):
    id: int
    overall_score: int
    grammar_score: int
    fluency_score: int
    vocabulary_score: int
    confidence_score: int
    corrections: list[SpeakingCorrection]
    strengths: list[str]
    improvements: list[str]
    coach_feedback: str
    transcript: str
    duration_seconds: int
    created_at: datetime


class SpeakingEvaluationHistoryResponse(BaseModel):
    evaluations: list[SpeakingEvaluationResponse]
    evaluations_completed: int
    average_speaking_score: float
    best_speaking_score: int
