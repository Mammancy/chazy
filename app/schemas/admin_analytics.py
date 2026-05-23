from pydantic import BaseModel


class AdminMetricResponse(BaseModel):
    label: str
    value: str
    detail: str


class AdminTrendPointResponse(BaseModel):
    date: str
    value: int


class AdminCategoryCountResponse(BaseModel):
    category: str
    count: int


class AdminConversationAnalyticsResponse(BaseModel):
    average_session_duration_minutes: float
    median_session_duration_minutes: float
    average_messages_per_conversation: float
    active_conversation_days: int
    feature_usage: list[AdminCategoryCountResponse]
    engagement_by_hour: list[AdminTrendPointResponse]


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
    learning_issue_categories: list[AdminCategoryCountResponse]
    conversation_analytics: AdminConversationAnalyticsResponse
    trends: dict[str, list[AdminTrendPointResponse]]
    api_consumption: AdminApiConsumptionResponse
    system_health: AdminSystemHealthResponse
