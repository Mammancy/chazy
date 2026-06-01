from datetime import datetime

from pydantic import BaseModel, Field


class CommunityUserSummary(BaseModel):
    id: int
    display_name: str
    initials: str
    level: str
    xp: int
    streak: int
    achievement_count: int
    vocabulary_count: int
    lessons_completed: int = 0
    pronunciation_sessions: int
    last_active_at: datetime | None = None


class CommunityActivity(BaseModel):
    id: str
    type: str
    user: CommunityUserSummary
    message: str
    occurred_at: datetime
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class PublicAchievement(BaseModel):
    id: int
    title: str
    description: str
    category: str
    points: int
    awarded_at: datetime


class PublicProfile(BaseModel):
    user: CommunityUserSummary
    achievements: list[PublicAchievement]
    recent_activity: list[CommunityActivity]


class CommunityFeedResponse(BaseModel):
    activities: list[CommunityActivity]
    total: int
    limit: int
    offset: int


class CommunityUsersResponse(BaseModel):
    users: list[CommunityUserSummary]
    total: int
    limit: int
    offset: int
