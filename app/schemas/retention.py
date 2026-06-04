from datetime import date

from pydantic import BaseModel


class DailyMissionResponse(BaseModel):
    id: str
    title: str
    description: str
    progress: int
    target: int
    xp_reward: int
    badge: str
    completed: bool


class WeeklyGoalResponse(BaseModel):
    id: str
    title: str
    progress: int
    target: int
    completed: bool


class CelebrationResponse(BaseModel):
    type: str
    title: str
    message: str


class DailyCheckInResponse(BaseModel):
    show: bool
    message: str
    current_streak: int
    xp_earned_yesterday: int
    checkin_date: date


class RetentionSummaryResponse(BaseModel):
    user_id: int
    today: date
    xp: int
    level: int
    level_label: str
    next_level_xp: int
    xp_to_next_level: int
    current_streak: int
    longest_streak: int
    freeze_tokens: int
    daily_checkin: DailyCheckInResponse
    daily_missions: list[DailyMissionResponse]
    weekly_goals: list[WeeklyGoalResponse]
    celebrations: list[CelebrationResponse]

