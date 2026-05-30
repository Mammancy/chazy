from pydantic import BaseModel, Field


class LeaderboardUserResponse(BaseModel):
    id: int
    rank: int
    name: str
    xp: int
    streak: int
    level: str
    achievement_points: int = Field(default=0)
    speaking_challenges_completed: int = Field(default=0)
    vocabulary_words: int = Field(default=0)
    pronunciation_attempts: int = Field(default=0)


class LeaderboardResponse(BaseModel):
    users: list[LeaderboardUserResponse]
    current_user_rank: int | None = None
