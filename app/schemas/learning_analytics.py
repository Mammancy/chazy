from datetime import datetime

from pydantic import BaseModel


class LearningIssueResponse(BaseModel):
    id: int
    category: str
    issue_key: str
    label: str
    example: str | None
    recommendation: str
    count: int
    last_seen_at: datetime

    model_config = {"from_attributes": True}


class PracticeRecommendationResponse(BaseModel):
    title: str
    description: str
    category: str
    priority: int


class LearningAnalyticsResponse(BaseModel):
    session_id: str
    user_id: int | None
    total_issues: int
    recurring_grammar_mistakes: list[LearningIssueResponse]
    vocabulary_weaknesses: list[LearningIssueResponse]
    sentence_structure_issues: list[LearningIssueResponse]
    recommendations: list[PracticeRecommendationResponse]
