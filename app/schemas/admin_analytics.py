from pydantic import BaseModel


class AdminMetricResponse(BaseModel):
    label: str
    value: str
    detail: str


class AdminTrendPointResponse(BaseModel):
    date: str
    value: int


class AdminAnalyticsSectionResponse(BaseModel):
    title: str
    metrics: list[AdminMetricResponse]


class AdminApiConsumptionResponse(BaseModel):
    estimated_total_tokens: int
    estimated_prompt_tokens: int
    estimated_completion_tokens: int
    estimated_requests: int
    estimated_cost_usd: float
    detail: str


class AdminSystemHealthResponse(BaseModel):
    status: str
    database_status: str
    environment: str
    version: str
    table_counts: dict[str, int]


class AdminAnalyticsDashboardResponse(BaseModel):
    generated_at: str
    window_days: int
    user_growth: AdminAnalyticsSectionResponse
    engagement: AdminAnalyticsSectionResponse
    conversation_volume: AdminAnalyticsSectionResponse
    challenge_participation: AdminAnalyticsSectionResponse
    learning_progress: AdminAnalyticsSectionResponse
    trends: dict[str, list[AdminTrendPointResponse]]
    api_consumption: AdminApiConsumptionResponse
    system_health: AdminSystemHealthResponse
