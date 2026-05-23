from pydantic import BaseModel


class DashboardMetricResponse(BaseModel):
    label: str
    value: str
    detail: str


class DashboardInsightResponse(BaseModel):
    title: str
    body: str
    category: str


class FluencyDashboardResponse(BaseModel):
    session_id: str
    user_id: int | None
    grammar_progress: DashboardMetricResponse
    vocabulary_growth: DashboardMetricResponse
    completed_conversations: DashboardMetricResponse
    challenge_streak: DashboardMetricResponse
    personalized_insights: list[DashboardInsightResponse]
