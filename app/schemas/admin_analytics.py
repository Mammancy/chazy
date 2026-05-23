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


class AdminUserUsageResponse(BaseModel):
    identity: str
    display_name: str
    request_count: int
    estimated_tokens: int
    estimated_cost_usd: float
    last_seen_at: str | None


class AdminOpenAIUsageResponse(BaseModel):
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    request_count: int
    average_tokens_per_request: float
    estimated_cost_usd: float
    token_trend: list[AdminTrendPointResponse]
    request_trend: list[AdminTrendPointResponse]
    cost_trend: list[AdminTrendPointResponse]
    user_usage: list[AdminUserUsageResponse]
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
    openai_usage: AdminOpenAIUsageResponse
    system_health: AdminSystemHealthResponse
