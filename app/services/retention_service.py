from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.achievement import AchievementAward
from app.models.practice_session import PracticeSession
from app.models.retention import RetentionState
from app.models.speaking_challenge import SpeakingChallengeCompletion
from app.models.user import User
from app.models.vocabulary_notebook import VocabularyNotebookEntry, VocabularyReviewSession
from app.schemas.retention import (
    CelebrationResponse,
    DailyCheckInResponse,
    DailyMissionResponse,
    RetentionSummaryResponse,
    WeeklyGoalResponse,
)
from app.services.level_service import level_label_for_xp, level_number_for_xp, next_level_xp
from app.services.speaking_challenge_service import SpeakingChallengeService


class RetentionService:
    def __init__(self, db: Session):
        self.db = db

    def summary(self, *, user: User) -> RetentionSummaryResponse:
        today = date.today()
        state = self._state(user.id)
        session_id = f"chazy-user-{user.id}"
        streak = SpeakingChallengeService(self.db).get_streak(session_id=session_id, user_id=user.id)
        xp_before = self._xp(user.id)
        previous_level = level_number_for_xp(xp_before)
        daily_missions = self._daily_missions(user_id=user.id, today=today)
        celebrations = self._award_completed_missions(
            user_id=user.id,
            session_id=session_id,
            missions=daily_missions,
            today=today,
            state=state,
        )
        xp = self._xp(user.id)
        current_level = level_number_for_xp(xp)
        if current_level > previous_level:
            celebrations.append(
                CelebrationResponse(
                    type="new_level",
                    title=f"Level {current_level} reached",
                    message="Your consistent practice raised your Confidence level.",
                )
            )

        daily_checkin = self._checkin(user_id=user.id, state=state, streak=streak.current_streak, today=today)
        self.db.add(state)
        self.db.commit()

        target_xp = next_level_xp(xp)
        return RetentionSummaryResponse(
            user_id=user.id,
            today=today,
            xp=xp,
            level=current_level,
            level_label=level_label_for_xp(xp),
            next_level_xp=target_xp,
            xp_to_next_level=max(target_xp - xp, 0),
            current_streak=streak.current_streak,
            longest_streak=streak.longest_streak,
            freeze_tokens=state.freeze_tokens,
            daily_checkin=daily_checkin,
            daily_missions=daily_missions,
            weekly_goals=self._weekly_goals(user_id=user.id, today=today),
            celebrations=celebrations,
        )

    def _state(self, user_id: int) -> RetentionState:
        state = self.db.scalar(select(RetentionState).where(RetentionState.user_id == user_id).limit(1))
        if state is not None:
            return state
        state = RetentionState(user_id=user_id, freeze_tokens=0)
        self.db.add(state)
        self.db.flush()
        return state

    def _checkin(self, *, user_id: int, state: RetentionState, streak: int, today: date) -> DailyCheckInResponse:
        show = state.last_checkin_date != today
        state.last_checkin_date = today
        return DailyCheckInResponse(
            show=show,
            message="Welcome back",
            current_streak=streak,
            xp_earned_yesterday=self._xp_earned_on(user_id=user_id, active_date=today - timedelta(days=1)),
            checkin_date=today,
        )

    def _daily_missions(self, *, user_id: int, today: date) -> list[DailyMissionResponse]:
        practice_minutes = self._practice_minutes(user_id=user_id, start=today, end=today + timedelta(days=1))
        vocabulary_words = self._vocabulary_words(user_id=user_id, start=today, end=today + timedelta(days=1))
        speaking_challenges = self._speaking_challenges(user_id=user_id, start=today, end=today + timedelta(days=1))
        return [
            DailyMissionResponse(
                id="practice_5_minutes",
                title="Practice 5 minutes",
                description="Complete five minutes of speaking practice today.",
                progress=min(practice_minutes, 5),
                target=5,
                xp_reward=20,
                badge="Daily Practice",
                completed=practice_minutes >= 5,
            ),
            DailyMissionResponse(
                id="learn_5_vocabulary_words",
                title="Learn 5 vocabulary words",
                description="Save or learn five vocabulary words today.",
                progress=min(vocabulary_words, 5),
                target=5,
                xp_reward=20,
                badge="Word Builder",
                completed=vocabulary_words >= 5,
            ),
            DailyMissionResponse(
                id="complete_1_speaking_challenge",
                title="Complete 1 speaking challenge",
                description="Finish one daily speaking challenge.",
                progress=min(speaking_challenges, 1),
                target=1,
                xp_reward=25,
                badge="Speaking Habit",
                completed=speaking_challenges >= 1,
            ),
        ]

    def _weekly_goals(self, *, user_id: int, today: date) -> list[WeeklyGoalResponse]:
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=7)
        return [
            WeeklyGoalResponse(
                id="weekly_practice_sessions",
                title="3 practice sessions",
                progress=min(self._completed_practice_sessions(user_id=user_id, start=start, end=end), 3),
                target=3,
                completed=self._completed_practice_sessions(user_id=user_id, start=start, end=end) >= 3,
            ),
            WeeklyGoalResponse(
                id="weekly_vocabulary_reviews",
                title="30 vocabulary reviews",
                progress=min(self._vocabulary_reviews(user_id=user_id, start=start, end=end), 30),
                target=30,
                completed=self._vocabulary_reviews(user_id=user_id, start=start, end=end) >= 30,
            ),
            WeeklyGoalResponse(
                id="weekly_speaking_minutes",
                title="60 speaking minutes",
                progress=min(self._practice_minutes(user_id=user_id, start=start, end=end), 60),
                target=60,
                completed=self._practice_minutes(user_id=user_id, start=start, end=end) >= 60,
            ),
        ]

    def _award_completed_missions(
        self,
        *,
        user_id: int,
        session_id: str,
        missions: list[DailyMissionResponse],
        today: date,
        state: RetentionState,
    ) -> list[CelebrationResponse]:
        celebrations: list[CelebrationResponse] = []
        all_completed = all(mission.completed for mission in missions)
        for mission in missions:
            if not mission.completed:
                continue
            award_key = f"daily_mission_{mission.id}_{today.isoformat()}"
            if self._award_exists(user_id=user_id, session_id=session_id, achievement_key=award_key):
                continue
            self.db.add(
                AchievementAward(
                    session_id=session_id,
                    user_id=user_id,
                    achievement_key=award_key,
                    category="daily_mission",
                    title=mission.badge,
                    description=mission.title,
                    points=mission.xp_reward,
                    metadata_json={"mission_id": mission.id, "mission_date": today.isoformat()},
                )
            )
            celebrations.append(
                CelebrationResponse(
                    type="mission_complete",
                    title=f"{mission.badge} complete",
                    message=f"{mission.title} earned {mission.xp_reward} XP.",
                )
            )

        if all_completed and state.last_freeze_earned_date != today:
            state.freeze_tokens += 1
            state.last_freeze_earned_date = today
            celebrations.append(
                CelebrationResponse(
                    type="new_badge",
                    title="Streak freeze earned",
                    message="All daily missions completed. One freeze token was added.",
                )
            )
        self.db.flush()
        return celebrations

    def _award_exists(self, *, user_id: int, session_id: str, achievement_key: str) -> bool:
        return self.db.scalar(
            select(AchievementAward.id)
            .where(
                AchievementAward.user_id == user_id,
                AchievementAward.session_id == session_id,
                AchievementAward.achievement_key == achievement_key,
            )
            .limit(1)
        ) is not None

    def _xp(self, user_id: int) -> int:
        return sum(
            award.points
            for award in self.db.scalars(select(AchievementAward).where(AchievementAward.user_id == user_id)).all()
        )

    def _xp_earned_on(self, *, user_id: int, active_date: date) -> int:
        start = self._start(active_date)
        end = self._start(active_date + timedelta(days=1))
        return sum(
            award.points
            for award in self.db.scalars(
                select(AchievementAward).where(
                    AchievementAward.user_id == user_id,
                    AchievementAward.awarded_at >= start,
                    AchievementAward.awarded_at < end,
                )
            ).all()
        )

    def _practice_minutes(self, *, user_id: int, start: date, end: date) -> int:
        rows = self.db.scalars(
            select(PracticeSession).where(
                PracticeSession.status == "completed",
                or_(PracticeSession.requester_user_id == user_id, PracticeSession.partner_user_id == user_id),
                PracticeSession.updated_at >= self._start(start),
                PracticeSession.updated_at < self._start(end),
            )
        ).all()
        return sum(row.duration_minutes for row in rows)

    def _completed_practice_sessions(self, *, user_id: int, start: date, end: date) -> int:
        return self.db.query(PracticeSession).filter(
            PracticeSession.status == "completed",
            or_(PracticeSession.requester_user_id == user_id, PracticeSession.partner_user_id == user_id),
            PracticeSession.updated_at >= self._start(start),
            PracticeSession.updated_at < self._start(end),
        ).count()

    def _vocabulary_words(self, *, user_id: int, start: date, end: date) -> int:
        return self.db.query(VocabularyNotebookEntry).filter(
            VocabularyNotebookEntry.user_id == user_id,
            VocabularyNotebookEntry.created_at >= self._start(start),
            VocabularyNotebookEntry.created_at < self._start(end),
        ).count()

    def _vocabulary_reviews(self, *, user_id: int, start: date, end: date) -> int:
        rows = self.db.scalars(
            select(VocabularyReviewSession).where(
                VocabularyReviewSession.user_id == user_id,
                VocabularyReviewSession.completed_at >= self._start(start),
                VocabularyReviewSession.completed_at < self._start(end),
            )
        ).all()
        return sum(row.reviewed_count for row in rows)

    def _speaking_challenges(self, *, user_id: int, start: date, end: date) -> int:
        return self.db.query(SpeakingChallengeCompletion).filter(
            SpeakingChallengeCompletion.user_id == user_id,
            SpeakingChallengeCompletion.challenge_date >= start,
            SpeakingChallengeCompletion.challenge_date < end,
        ).count()

    @staticmethod
    def _start(active_date: date) -> datetime:
        return datetime.combine(active_date, time.min, tzinfo=timezone.utc)

