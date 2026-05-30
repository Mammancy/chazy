from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.achievement import AchievementAward
from app.models.pronunciation import PronunciationPracticeAttempt
from app.models.speaking_challenge import SpeakingChallengeCompletion
from app.models.user import User
from app.models.vocabulary_notebook import VocabularyNotebookEntry
from app.schemas.leaderboard import LeaderboardResponse, LeaderboardUserResponse
from app.services.speaking_challenge_service import SpeakingChallengeService


class LeaderboardService:
    def __init__(self, db: Session):
        self.db = db

    def get_leaderboard(self, *, current_user: User, limit: int = 25) -> LeaderboardResponse:
        active_users = self.db.scalars(
            select(User)
            .where(User.is_active.is_(True), User.role != "admin")
            .order_by(User.created_at.asc())
        ).all()
        if not active_users:
            return LeaderboardResponse(users=[], current_user_rank=None)

        user_ids = [user.id for user in active_users]
        achievement_points = self._sum_by_user(AchievementAward.user_id, AchievementAward.points, user_ids)
        challenge_counts = self._count_by_user(SpeakingChallengeCompletion.user_id, user_ids)
        vocabulary_counts = self._count_by_user(VocabularyNotebookEntry.user_id, user_ids)
        pronunciation_counts = self._count_by_user(PronunciationPracticeAttempt.user_id, user_ids)

        rows: list[LeaderboardUserResponse] = []
        streak_service = SpeakingChallengeService(self.db)
        for user in active_users:
            points = achievement_points.get(user.id, 0)
            completed_challenges = challenge_counts.get(user.id, 0)
            vocabulary_words = vocabulary_counts.get(user.id, 0)
            pronunciation_attempts = pronunciation_counts.get(user.id, 0)
            streak = streak_service.get_streak(session_id=f"chazy-user-{user.id}", user_id=user.id).current_streak
            xp = points + completed_challenges * 10 + vocabulary_words * 5 + pronunciation_attempts * 3
            rows.append(
                LeaderboardUserResponse(
                    id=user.id,
                    rank=0,
                    name=user.full_name or user.email or f"Confidence Learner {user.id}",
                    xp=xp,
                    streak=streak,
                    level=self._level_for_xp(xp),
                    achievement_points=points,
                    speaking_challenges_completed=completed_challenges,
                    vocabulary_words=vocabulary_words,
                    pronunciation_attempts=pronunciation_attempts,
                )
            )

        rows.sort(key=lambda row: (row.xp, row.streak, row.achievement_points), reverse=True)
        ranked_rows = [row.model_copy(update={"rank": index + 1}) for index, row in enumerate(rows)]
        current_user_rank = next((row.rank for row in ranked_rows if row.id == current_user.id), None)

        return LeaderboardResponse(users=ranked_rows[:limit], current_user_rank=current_user_rank)

    def _sum_by_user(self, user_column, value_column, user_ids: list[int]) -> dict[int, int]:
        result = self.db.execute(
            select(user_column, func.coalesce(func.sum(value_column), 0))
            .where(user_column.in_(user_ids))
            .group_by(user_column)
        ).all()
        return {int(user_id): int(total or 0) for user_id, total in result if user_id is not None}

    def _count_by_user(self, user_column, user_ids: list[int]) -> dict[int, int]:
        result = self.db.execute(
            select(user_column, func.count())
            .where(user_column.in_(user_ids))
            .group_by(user_column)
        ).all()
        return {int(user_id): int(total or 0) for user_id, total in result if user_id is not None}

    @staticmethod
    def _level_for_xp(xp: int) -> str:
        if xp >= 2500:
            return "Expert Speaker"
        if xp >= 1200:
            return "Advanced Speaker"
        if xp >= 500:
            return "Confident Speaker"
        if xp >= 150:
            return "Growing Speaker"
        return "New Speaker"
