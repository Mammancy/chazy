from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.achievement import AchievementAward
from app.models.placement_assessment import PlacementAssessmentSession
from app.models.pronunciation import PronunciationPracticeAttempt, PronunciationPracticeSession
from app.models.speaking_challenge import SpeakingChallengeCompletion
from app.models.user import User
from app.models.vocabulary_notebook import VocabularyNotebookEntry
from app.schemas.community import (
    CommunityActivity,
    CommunityFeedResponse,
    CommunityUserSummary,
    CommunityUsersResponse,
    PublicAchievement,
    PublicProfile,
)
from app.services.speaking_challenge_service import SpeakingChallengeService


class CommunityService:
    def __init__(self, db: Session):
        self.db = db

    def get_feed(self, *, limit: int = 25, offset: int = 0) -> CommunityFeedResponse:
        users = self._public_users()
        summaries = self._summary_map(users)
        activities: list[CommunityActivity] = []

        user_ids = list(summaries)
        if user_ids:
            activities.extend(self._achievement_activities(user_ids, summaries))
            activities.extend(self._challenge_activities(user_ids, summaries))
            activities.extend(self._vocabulary_activities(user_ids, summaries))
            activities.extend(self._pronunciation_activities(user_ids, summaries))
            activities.extend(self._assessment_activities(user_ids, summaries))
            activities.extend(self._streak_activities(users, summaries))

        activities.sort(key=lambda item: self._utc_sort_key(item.occurred_at), reverse=True)
        total = len(activities)
        return CommunityFeedResponse(
            activities=activities[offset : offset + limit],
            total=total,
            limit=limit,
            offset=offset,
        )

    def list_users(self, *, limit: int = 25, offset: int = 0) -> CommunityUsersResponse:
        users = self._public_users()
        summaries = list(self._summary_map(users).values())
        summaries.sort(key=lambda user: (-user.xp, -user.streak, user.display_name.lower(), user.id))
        total = len(summaries)
        return CommunityUsersResponse(users=summaries[offset : offset + limit], total=total, limit=limit, offset=offset)

    def get_public_profile(self, user_id: int) -> PublicProfile:
        user = self.db.get(User, user_id)
        if user is None or not user.is_active or not user.public_profile_visible or user.role == "admin":
            raise ValueError("Public profile not found.")

        summary = self._summary_map([user])[user.id]
        achievements = [
            PublicAchievement(
                id=award.id,
                title=award.title,
                description=award.description,
                category=award.category,
                points=award.points,
                awarded_at=award.awarded_at,
            )
            for award in self.db.scalars(
                select(AchievementAward)
                .where(AchievementAward.user_id == user.id)
                .order_by(AchievementAward.awarded_at.desc(), AchievementAward.id.desc())
                .limit(12)
            ).all()
        ]
        recent_activity = self.get_feed(limit=100, offset=0).activities
        user_activity = [activity for activity in recent_activity if activity.user.id == user.id][:10]
        return PublicProfile(user=summary, achievements=achievements, recent_activity=user_activity)

    def _public_users(self) -> list[User]:
        return list(
            self.db.scalars(
                select(User)
                .where(
                    User.is_active.is_(True),
                    User.public_profile_visible.is_(True),
                    User.role != "admin",
                )
                .order_by(User.created_at.desc(), User.id.desc())
            ).all()
        )

    def _summary_map(self, users: list[User]) -> dict[int, CommunityUserSummary]:
        user_ids = [user.id for user in users]
        if not user_ids:
            return {}

        achievement_points = self._sum_by_user(AchievementAward.user_id, AchievementAward.points, user_ids)
        achievement_counts = self._count_by_user(AchievementAward.user_id, user_ids)
        challenge_counts = self._count_by_user(SpeakingChallengeCompletion.user_id, user_ids)
        vocabulary_counts = self._count_by_user(VocabularyNotebookEntry.user_id, user_ids)
        pronunciation_counts = self._count_by_user(PronunciationPracticeAttempt.user_id, user_ids)
        last_activity = self._last_activity_by_user(user_ids)
        streak_service = SpeakingChallengeService(self.db)

        summaries = {}
        for user in users:
            display_name = self._display_name(user)
            points = achievement_points.get(user.id, 0)
            completed_challenges = challenge_counts.get(user.id, 0)
            vocabulary_words = vocabulary_counts.get(user.id, 0)
            pronunciation_attempts = pronunciation_counts.get(user.id, 0)
            streak = streak_service.get_streak(session_id=f"chazy-user-{user.id}", user_id=user.id).current_streak
            xp = points + completed_challenges * 10 + vocabulary_words * 5 + pronunciation_attempts * 3
            summaries[user.id] = CommunityUserSummary(
                id=user.id,
                display_name=display_name,
                initials=self._initials(display_name),
                level=self._level_for_xp(xp),
                xp=xp,
                streak=streak,
                achievement_count=achievement_counts.get(user.id, 0),
                vocabulary_count=vocabulary_words,
                lessons_completed=0,
                pronunciation_sessions=pronunciation_attempts,
                last_active_at=last_activity.get(user.id) or user.updated_at or user.created_at,
            )
        return summaries

    def _achievement_activities(
        self,
        user_ids: list[int],
        summaries: dict[int, CommunityUserSummary],
    ) -> list[CommunityActivity]:
        rows = self.db.scalars(
            select(AchievementAward)
            .where(AchievementAward.user_id.in_(user_ids))
            .order_by(AchievementAward.awarded_at.desc(), AchievementAward.id.desc())
            .limit(40)
        ).all()
        return [
            self._activity(
                activity_id=f"achievement-{row.id}",
                activity_type="achievement_earned",
                user=summaries[row.user_id],
                message=f"{summaries[row.user_id].display_name} earned {row.title}",
                occurred_at=row.awarded_at,
                metadata={"achievement": row.title, "points": row.points},
            )
            for row in rows
            if row.user_id in summaries
        ]

    def _challenge_activities(
        self,
        user_ids: list[int],
        summaries: dict[int, CommunityUserSummary],
    ) -> list[CommunityActivity]:
        rows = self.db.scalars(
            select(SpeakingChallengeCompletion)
            .where(SpeakingChallengeCompletion.user_id.in_(user_ids))
            .order_by(SpeakingChallengeCompletion.completed_at.desc(), SpeakingChallengeCompletion.id.desc())
            .limit(40)
        ).all()
        return [
            self._activity(
                activity_id=f"challenge-{row.id}",
                activity_type="challenge_completed",
                user=summaries[row.user_id],
                message=f"{summaries[row.user_id].display_name} completed today's speaking challenge",
                occurred_at=row.completed_at,
                metadata={"difficulty": row.difficulty, "spoken_seconds": row.spoken_seconds},
            )
            for row in rows
            if row.user_id in summaries
        ]

    def _vocabulary_activities(
        self,
        user_ids: list[int],
        summaries: dict[int, CommunityUserSummary],
    ) -> list[CommunityActivity]:
        rows = self.db.scalars(
            select(VocabularyNotebookEntry)
            .where(VocabularyNotebookEntry.user_id.in_(user_ids))
            .order_by(VocabularyNotebookEntry.created_at.desc(), VocabularyNotebookEntry.id.desc())
            .limit(40)
        ).all()
        return [
            self._activity(
                activity_id=f"vocabulary-{row.id}",
                activity_type="vocabulary_milestone",
                user=summaries[row.user_id],
                message=f"{summaries[row.user_id].display_name} added {row.word} to their vocabulary notebook",
                occurred_at=row.created_at,
                metadata={"word": row.word, "mastery_status": row.mastery_status},
            )
            for row in rows
            if row.user_id in summaries
        ]

    def _pronunciation_activities(
        self,
        user_ids: list[int],
        summaries: dict[int, CommunityUserSummary],
    ) -> list[CommunityActivity]:
        rows = self.db.scalars(
            select(PronunciationPracticeAttempt)
            .where(PronunciationPracticeAttempt.user_id.in_(user_ids))
            .order_by(PronunciationPracticeAttempt.created_at.desc(), PronunciationPracticeAttempt.id.desc())
            .limit(40)
        ).all()
        return [
            self._activity(
                activity_id=f"pronunciation-{row.id}",
                activity_type="pronunciation_completed",
                user=summaries[row.user_id],
                message=f"{summaries[row.user_id].display_name} completed a pronunciation session",
                occurred_at=row.created_at,
                metadata={"score": row.score, "scoring_status": row.scoring_status},
            )
            for row in rows
            if row.user_id in summaries
        ]

    def _assessment_activities(
        self,
        user_ids: list[int],
        summaries: dict[int, CommunityUserSummary],
    ) -> list[CommunityActivity]:
        rows = self.db.scalars(
            select(PlacementAssessmentSession)
            .where(
                PlacementAssessmentSession.user_id.in_(user_ids),
                PlacementAssessmentSession.completed_at.is_not(None),
            )
            .order_by(PlacementAssessmentSession.completed_at.desc(), PlacementAssessmentSession.id.desc())
            .limit(40)
        ).all()
        return [
            self._activity(
                activity_id=f"assessment-{row.id}",
                activity_type="assessment_completed",
                user=summaries[row.user_id],
                message=f"{summaries[row.user_id].display_name} completed a placement assessment",
                occurred_at=row.completed_at or row.created_at,
                metadata={"level": row.proficiency_level},
            )
            for row in rows
            if row.user_id in summaries
        ]

    def _streak_activities(
        self,
        users: list[User],
        summaries: dict[int, CommunityUserSummary],
    ) -> list[CommunityActivity]:
        activities = []
        streak_service = SpeakingChallengeService(self.db)
        for user in users:
            streak = streak_service.get_streak(session_id=f"chazy-user-{user.id}", user_id=user.id)
            if streak.current_streak <= 0:
                continue
            activities.append(
                self._activity(
                    activity_id=f"streak-{user.id}-{streak.current_streak}",
                    activity_type="streak_milestone",
                    user=summaries[user.id],
                    message=f"{summaries[user.id].display_name} reached a {streak.current_streak} day streak",
                    occurred_at=datetime.now(timezone.utc),
                    metadata={"streak": streak.current_streak},
                )
            )
        return activities

    def _last_activity_by_user(self, user_ids: list[int]) -> dict[int, datetime]:
        sources = [
            self.db.execute(
                select(AchievementAward.user_id, func.max(AchievementAward.awarded_at))
                .where(AchievementAward.user_id.in_(user_ids))
                .group_by(AchievementAward.user_id)
            ).all(),
            self.db.execute(
                select(SpeakingChallengeCompletion.user_id, func.max(SpeakingChallengeCompletion.completed_at))
                .where(SpeakingChallengeCompletion.user_id.in_(user_ids))
                .group_by(SpeakingChallengeCompletion.user_id)
            ).all(),
            self.db.execute(
                select(VocabularyNotebookEntry.user_id, func.max(VocabularyNotebookEntry.created_at))
                .where(VocabularyNotebookEntry.user_id.in_(user_ids))
                .group_by(VocabularyNotebookEntry.user_id)
            ).all(),
            self.db.execute(
                select(PronunciationPracticeSession.user_id, func.max(PronunciationPracticeSession.created_at))
                .where(PronunciationPracticeSession.user_id.in_(user_ids))
                .group_by(PronunciationPracticeSession.user_id)
            ).all(),
        ]
        result: dict[int, datetime] = {}
        for rows in sources:
            for user_id, occurred_at in rows:
                if user_id is None or occurred_at is None:
                    continue
                if user_id not in result or self._utc_sort_key(occurred_at) > self._utc_sort_key(result[user_id]):
                    result[int(user_id)] = occurred_at
        return result

    def _count_by_user(self, user_column, user_ids: list[int]) -> dict[int, int]:
        rows = self.db.execute(
            select(user_column, func.count())
            .where(user_column.in_(user_ids))
            .group_by(user_column)
        ).all()
        return {int(user_id): int(total or 0) for user_id, total in rows if user_id is not None}

    def _sum_by_user(self, user_column, value_column, user_ids: list[int]) -> dict[int, int]:
        rows = self.db.execute(
            select(user_column, func.coalesce(func.sum(value_column), 0))
            .where(user_column.in_(user_ids))
            .group_by(user_column)
        ).all()
        return {int(user_id): int(total or 0) for user_id, total in rows if user_id is not None}

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

    @staticmethod
    def _activity(
        *,
        activity_id: str,
        activity_type: str,
        user: CommunityUserSummary,
        message: str,
        occurred_at: datetime,
        metadata: dict[str, str | int | float | bool | None],
    ) -> CommunityActivity:
        return CommunityActivity(
            id=activity_id,
            type=activity_type,
            user=user,
            message=message,
            occurred_at=occurred_at,
            metadata=metadata,
        )

    @staticmethod
    def _display_name(user: User) -> str:
        return user.full_name or f"Confidence Learner {user.id}"

    @staticmethod
    def _initials(name: str) -> str:
        parts = [part[0].upper() for part in name.split() if part]
        return "".join(parts[:2]) or "C"

    @staticmethod
    def _utc_sort_key(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
