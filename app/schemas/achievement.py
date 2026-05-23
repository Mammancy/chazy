from datetime import datetime

from pydantic import BaseModel, Field


class AchievementEvaluateRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    user_id: int | None = Field(default=None, ge=1)


class AchievementAwardResponse(BaseModel):
    id: int
    session_id: str
    user_id: int | None
    achievement_key: str
    category: str
    title: str
    description: str
    points: int
    metadata_json: dict | None
    awarded_at: datetime

    model_config = {"from_attributes": True}


class AchievementProgressResponse(BaseModel):
    achievement_key: str
    category: str
    title: str
    description: str
    current_value: int
    target_value: int
    completed: bool
    points: int


class AchievementSummaryResponse(BaseModel):
    session_id: str
    user_id: int | None
    total_points: int
    awarded_count: int
    badges_by_category: dict[str, int]
    recent_awards: list[AchievementAwardResponse]
    next_milestones: list[AchievementProgressResponse]
    newly_awarded: list[AchievementAwardResponse]
