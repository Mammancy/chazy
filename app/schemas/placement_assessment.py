from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class PlacementQuestionResponse(BaseModel):
    question_id: str
    skill: str
    difficulty: str
    prompt: str
    question_type: str
    options: list[str] = Field(default_factory=list)


class PlacementAssessmentStartRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    user_id: int | None = Field(default=None, ge=1)


class PlacementAssessmentStartResponse(BaseModel):
    assessment_session_id: int
    session_id: str
    user_id: int | None
    status: str
    current_step: int
    total_questions: int
    first_question: PlacementQuestionResponse
    created_at: datetime


class PlacementAnswerSubmitRequest(BaseModel):
    question_id: str = Field(..., min_length=1)
    answer: str = Field(..., min_length=1)


class PlacementAnswerFeedbackResponse(BaseModel):
    question_id: str
    skill: str
    score: int
    max_score: int
    feedback: str
    next_question: PlacementQuestionResponse | None = None
    completed: bool


class PlacementLearningPlanResponse(BaseModel):
    level: str
    focus_areas: list[str]
    weekly_goals: list[str]
    recommended_modes: list[str]
    starter_plan: list[str]


class PlacementAssessmentResultResponse(BaseModel):
    assessment_session_id: int
    session_id: str
    user_id: int | None
    status: str
    proficiency_level: str
    skill_scores: dict[str, int]
    learning_plan: PlacementLearningPlanResponse
    completed_at: datetime | None


class PlacementAssessmentStateResponse(BaseModel):
    assessment_session_id: int
    session_id: str
    status: str
    current_step: int
    total_questions: int
    next_question: PlacementQuestionResponse | None
    result: PlacementAssessmentResultResponse | None
    metadata: dict[str, Any] = Field(default_factory=dict)
