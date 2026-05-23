from pydantic import BaseModel


class RecommendationItemResponse(BaseModel):
    title: str
    description: str
    category: str
    priority: int
    reason: str
    action_label: str


class TargetedPracticeTopicResponse(BaseModel):
    topic: str
    prompt: str
    focus_area: str
    difficulty: str
    estimated_minutes: int


class RecommendationSignalResponse(BaseModel):
    mistake_count: int
    completed_challenges: int
    average_fluency_score: int | None
    conversation_count: int
    learning_goals: list[str]


class PersonalizedRecommendationResponse(BaseModel):
    session_id: str
    user_id: int | None
    daily_recommendations: list[RecommendationItemResponse]
    targeted_practice_topics: list[TargetedPracticeTopicResponse]
    improvement_suggestions: list[RecommendationItemResponse]
    signals: RecommendationSignalResponse
