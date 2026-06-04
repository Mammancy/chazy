from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.practice_session import PracticeSession
from app.models.retention import RetentionState
from app.models.speaking_challenge import SpeakingChallenge, SpeakingChallengeCompletion
from app.schemas.speaking_challenge import (
    DailySpeakingChallengesResponse,
    DailySpeakingStreakSyncCreate,
    SpeakingChallengeCompletionCreate,
    SpeakingChallengeCompletionResponse,
    SpeakingChallengeResponse,
    SpeakingChallengeStreakResponse,
)


DEFAULT_CHALLENGES = [
    {
        "difficulty": "beginner",
        "title": "My Morning",
        "prompt": "Talk for one minute about your morning routine. Use simple present tense and include three activities.",
        "suggested_duration_seconds": 60,
        "focus_area": "simple present",
    },
    {
        "difficulty": "beginner",
        "title": "Favorite Food",
        "prompt": "Describe your favorite food. Say what it tastes like, when you eat it, and why you like it.",
        "suggested_duration_seconds": 60,
        "focus_area": "describing preferences",
    },
    {
        "difficulty": "intermediate",
        "title": "A Helpful Person",
        "prompt": "Speak for two minutes about someone who helped you recently. Explain the situation, what they did, and how you felt.",
        "suggested_duration_seconds": 120,
        "focus_area": "past tense storytelling",
    },
    {
        "difficulty": "intermediate",
        "title": "Solving a Problem",
        "prompt": "Describe a problem at school, work, or home. Explain two possible solutions and which one you would choose.",
        "suggested_duration_seconds": 120,
        "focus_area": "structured opinions",
    },
    {
        "difficulty": "advanced",
        "title": "Technology and Learning",
        "prompt": "Discuss how technology changes the way people learn languages. Give benefits, risks, and your own recommendation.",
        "suggested_duration_seconds": 180,
        "focus_area": "balanced argument",
    },
    {
        "difficulty": "advanced",
        "title": "Community Leadership",
        "prompt": "Imagine you are leading a community project. Explain the goal, the challenges, and how you would motivate people.",
        "suggested_duration_seconds": 180,
        "focus_area": "persuasive speaking",
    },
]


class SpeakingChallengeService:
    def __init__(self, db: Session):
        self.db = db

    def seed_default_challenges(self) -> None:
        existing_titles = {
            row[0]
            for row in self.db.query(SpeakingChallenge.title).filter(
                SpeakingChallenge.title.in_([item["title"] for item in DEFAULT_CHALLENGES])
            )
        }
        for item in DEFAULT_CHALLENGES:
            if item["title"] in existing_titles:
                continue
            self.db.add(SpeakingChallenge(**item))
        self.db.commit()

    def get_daily_challenges(
        self,
        session_id: str,
        user_id: int | None = None,
        challenge_date: date | None = None,
    ) -> DailySpeakingChallengesResponse:
        active_date = challenge_date or date.today()
        completed_keys = {
            row.difficulty
            for row in self._completion_query(session_id, user_id).filter(
                SpeakingChallengeCompletion.challenge_date == active_date
            )
        }
        challenges = [
            self._challenge_response(challenge, active_date, challenge.difficulty in completed_keys)
            for challenge in self._select_daily_challenges(active_date)
        ]
        return DailySpeakingChallengesResponse(
            session_id=session_id,
            user_id=user_id,
            challenge_date=active_date,
            challenges=challenges,
            streak=self.get_streak(session_id, user_id, active_date),
        )

    def complete_challenge(
        self,
        challenge_id: int,
        payload: SpeakingChallengeCompletionCreate,
        challenge_date: date | None = None,
    ) -> SpeakingChallengeCompletionResponse:
        challenge = self.db.get(SpeakingChallenge, challenge_id)
        if challenge is None:
            raise ValueError("Speaking challenge not found.")

        active_date = challenge_date or date.today()
        completion = SpeakingChallengeCompletion(
            challenge_id=challenge.id,
            client_session_id=payload.session_id,
            user_id=payload.user_id,
            difficulty=challenge.difficulty,
            challenge_date=active_date,
            spoken_seconds=payload.spoken_seconds,
            reflection=payload.reflection,
        )
        self.db.add(completion)
        try:
            self.db.commit()
            self.db.refresh(completion)
        except IntegrityError:
            self.db.rollback()
            completion = self._completion_query(payload.session_id, payload.user_id).filter(
                SpeakingChallengeCompletion.challenge_date == active_date,
                SpeakingChallengeCompletion.difficulty == challenge.difficulty,
            ).one()

        return SpeakingChallengeCompletionResponse(
            completion_id=completion.id,
            challenge_id=completion.challenge_id,
            difficulty=completion.difficulty,
            challenge_date=completion.challenge_date,
            completed_at=completion.completed_at,
            streak=self.get_streak(payload.session_id, payload.user_id, active_date),
        )

    def get_streak(
        self,
        session_id: str,
        user_id: int | None = None,
        today: date | None = None,
    ) -> SpeakingChallengeStreakResponse:
        active_today = today or date.today()
        completed_dates = [
            row[0]
            for row in self._completion_query(session_id, user_id)
            .with_entities(SpeakingChallengeCompletion.challenge_date)
            .distinct()
            .order_by(SpeakingChallengeCompletion.challenge_date.desc())
            .all()
        ]
        completed_set = set(completed_dates) | self._practice_session_activity_dates(user_id)
        completed_set = self._apply_streak_freeze(user_id=user_id, active_today=active_today, completed_set=completed_set)
        current_streak = 0
        cursor = active_today
        if cursor not in completed_set:
            cursor = active_today - timedelta(days=1)
        while cursor in completed_set:
            current_streak += 1
            cursor -= timedelta(days=1)

        longest_streak = 0
        running = 0
        previous = None
        for completed_date in sorted(completed_set):
            if previous is not None and completed_date == previous + timedelta(days=1):
                running += 1
            else:
                running = 1
            longest_streak = max(longest_streak, running)
            previous = completed_date

        return SpeakingChallengeStreakResponse(
            session_id=session_id,
            user_id=user_id,
            current_streak=current_streak,
            longest_streak=longest_streak,
            completed_today=active_today in completed_set,
            last_completed_date=max(completed_set) if completed_set else None,
        )

    def sync_daily_speaking_streak(self, payload: DailySpeakingStreakSyncCreate) -> None:
        # Android can count chat-message speaking practice before the backend has
        # a dedicated daily streak table. Accept the sync payload so clients can
        # safely flush their offline queue; challenge-derived streaks still come
        # from SpeakingChallengeCompletion records.
        return None

    def _select_daily_challenges(self, challenge_date: date) -> list[SpeakingChallenge]:
        rows = self.db.query(SpeakingChallenge).order_by(SpeakingChallenge.id).all()
        selected = []
        for difficulty in ("beginner", "intermediate", "advanced"):
            matching = [row for row in rows if row.difficulty == difficulty]
            if not matching:
                continue
            selected.append(matching[challenge_date.toordinal() % len(matching)])
        return selected

    def _completion_query(self, session_id: str, user_id: int | None):
        query = self.db.query(SpeakingChallengeCompletion).filter(
            SpeakingChallengeCompletion.client_session_id == session_id
        )
        if user_id is None:
            query = query.filter(SpeakingChallengeCompletion.user_id.is_(None))
        else:
            query = query.filter(SpeakingChallengeCompletion.user_id == user_id)
        return query

    def _practice_session_activity_dates(self, user_id: int | None) -> set[date]:
        if user_id is None:
            return set()

        rows = self.db.query(PracticeSession).filter(
            PracticeSession.status == "completed",
            or_(PracticeSession.requester_user_id == user_id, PracticeSession.partner_user_id == user_id),
        ).all()
        activity_dates = set()
        for row in rows:
            activity_at = row.updated_at or row.scheduled_at
            activity_dates.add(activity_at.date())
        return activity_dates

    def _apply_streak_freeze(self, *, user_id: int | None, active_today: date, completed_set: set[date]) -> set[date]:
        if user_id is None:
            return completed_set
        missed_date = active_today - timedelta(days=1)
        previous_active_date = active_today - timedelta(days=2)
        if active_today in completed_set or missed_date in completed_set or previous_active_date not in completed_set:
            return completed_set

        state = self.db.scalar(select(RetentionState).where(RetentionState.user_id == user_id).limit(1))
        if state is None:
            return completed_set
        if state.last_freeze_used_date == missed_date:
            return completed_set | {missed_date}
        if state.freeze_tokens <= 0:
            return completed_set

        state.freeze_tokens -= 1
        state.last_freeze_used_date = missed_date
        self.db.add(state)
        self.db.commit()
        return completed_set | {missed_date}

    def _challenge_response(
        self,
        challenge: SpeakingChallenge,
        challenge_date: date,
        completed: bool,
    ) -> SpeakingChallengeResponse:
        return SpeakingChallengeResponse(
            id=challenge.id,
            difficulty=challenge.difficulty,
            title=challenge.title,
            prompt=challenge.prompt,
            suggested_duration_seconds=challenge.suggested_duration_seconds,
            focus_area=challenge.focus_area,
            challenge_date=challenge_date,
            completed=completed,
        )
