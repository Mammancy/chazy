from datetime import date, datetime

from pydantic import BaseModel, Field


class SpeakingChallengeResponse(BaseModel):
    id: int
    difficulty: str
    title: str
    prompt: str
    suggested_duration_seconds: int
    focus_area: str
    challenge_date: date
    completed: bool = False


class DailySpeakingChallengesResponse(BaseModel):
    session_id: str
    user_id: int | None
    challenge_date: date
    challenges: list[SpeakingChallengeResponse]
    streak: "SpeakingChallengeStreakResponse"


class SpeakingChallengeCompletionCreate(BaseModel):
    session_id: str = Field(..., min_length=1)
    user_id: int | None = Field(default=None, ge=1)
    spoken_seconds: int | None = Field(default=None, ge=0)
    reflection: str | None = None


class SpeakingChallengeCompletionResponse(BaseModel):
    completion_id: int
    challenge_id: int
    difficulty: str
    challenge_date: date
    completed_at: datetime
    streak: "SpeakingChallengeStreakResponse"


class SpeakingChallengeStreakResponse(BaseModel):
    session_id: str
    user_id: int | None
    current_streak: int
    longest_streak: int
    completed_today: bool
    last_completed_date: date | None = None
