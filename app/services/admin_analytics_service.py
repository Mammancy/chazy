from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.models.conversation import Conversation
from app.models.learning_analytics import LearningIssue
from app.models.message import Message
from app.models.placement_assessment import PlacementAssessmentSession
from app.models.pronunciation import PronunciationPracticeSession
from app.models.speaking_challenge import SpeakingChallengeCompletion
from app.models.user import User
from app.models.vocabulary_notebook import VocabularyNotebookEntry, VocabularyReviewSession
from app.schemas.admin_analytics import (
    AdminAnalyticsDashboardResponse,
    AdminAnalyticsSectionResponse,
    AdminApiConsumptionResponse,
    AdminMetricResponse,
    AdminSystemHealthResponse,
    AdminTrendPointResponse,
)


class AdminAnalyticsService:
    def __init__(self, db: Session):
        self.db = db

    def get_dashboard(self, window_days: int = 30) -> AdminAnalyticsDashboardResponse:
        window_days = max(1, min(window_days, 365))
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=window_days)

        users = self.db.query(User).all()
        messages = self.db.query(Message).all()
        conversations = self.db.query(Conversation).all()
        challenge_completions = self.db.query(SpeakingChallengeCompletion).all()
        vocabulary_entries = self.db.query(VocabularyNotebookEntry).all()
        review_sessions = self.db.query(VocabularyReviewSession).all()
        learning_issues = self.db.query(LearningIssue).all()
        placement_sessions = self.db.query(PlacementAssessmentSession).all()
        pronunciation_sessions = self.db.query(PronunciationPracticeSession).all()

        recent_users = [user for user in users if self._in_window(user.created_at, since)]
        recent_messages = [message for message in messages if self._in_window(message.created_at, since)]
        recent_conversations = [item for item in conversations if self._in_window(item.created_at, since)]
        recent_challenges = [item for item in challenge_completions if self._in_window(item.completed_at, since)]
        recent_vocabulary = [item for item in vocabulary_entries if self._in_window(item.created_at, since)]
        recent_reviews = [item for item in review_sessions if self._in_window(item.created_at, since)]

        active_user_ids = {message.user_id for message in recent_messages if message.user_id is not None}
        active_sessions = {
            metadata.get("session_id")
            for message in recent_messages
            for metadata in [message.metadata_json or {}]
            if metadata.get("session_id")
        }
        assistant_messages = [message for message in messages if message.role == "assistant"]
        user_messages = [message for message in messages if message.role == "user"]

        return AdminAnalyticsDashboardResponse(
            generated_at=now.isoformat(),
            window_days=window_days,
            user_growth=self._section(
                "User Growth",
                [
                    ("Total Users", len(users), f"{len(recent_users)} new users in the last {window_days} days."),
                    ("Active Learners", len(active_user_ids) + len(active_sessions), "Distinct signed-in users plus anonymous sessions with recent messages."),
                    ("Active Accounts", sum(1 for user in users if user.is_active), "Accounts currently marked active."),
                ],
            ),
            engagement=self._section(
                "Engagement",
                [
                    ("Practice Messages", len(user_messages), f"{sum(1 for item in recent_messages if item.role == 'user')} in the current window."),
                    ("Avg Messages/User", self._average(len(messages), max(len(users), 1)), "Total saved messages divided by registered users."),
                    ("Vocabulary Reviews", sum(item.reviewed_count for item in review_sessions), f"{sum(item.reviewed_count for item in recent_reviews)} reviews in the current window."),
                ],
            ),
            conversation_volume=self._section(
                "Conversation Volume",
                [
                    ("Conversations", len(conversations), f"{len(recent_conversations)} started in the last {window_days} days."),
                    ("Saved Messages", len(messages), f"{len(assistant_messages)} assistant replies and {len(user_messages)} learner messages."),
                    ("Avg Messages/Conversation", self._average(len(messages), max(len(conversations), 1)), "Conversation depth estimate from saved message count."),
                ],
            ),
            challenge_participation=self._section(
                "Challenge Participation",
                [
                    ("Completed Challenges", len(challenge_completions), f"{len(recent_challenges)} completed in the current window."),
                    ("Challenge Learners", self._distinct_challenge_learners(challenge_completions), "Distinct users and anonymous sessions with challenge completions."),
                    ("Speaking Seconds", sum(item.spoken_seconds or 0 for item in challenge_completions), "Total reported speaking practice time."),
                ],
            ),
            learning_progress=self._section(
                "Learning Progress",
                [
                    ("Vocabulary Words", len(vocabulary_entries), f"{len(recent_vocabulary)} saved in the current window."),
                    ("Mastered Words", sum(1 for item in vocabulary_entries if item.mastery_status == "mastered"), "Words marked mastered in vocabulary notebooks."),
                    ("Tracked Issues", len(learning_issues), "Recurring grammar, vocabulary, and sentence structure issues tracked."),
                    ("Completed Assessments", sum(1 for item in placement_sessions if item.status == "completed"), "Placement assessments completed by learners."),
                    ("Pronunciation Sessions", sum(1 for item in pronunciation_sessions if item.status == "completed"), "Completed pronunciation practice sessions."),
                ],
            ),
            trends={
                "new_users": self._daily_trend([user.created_at for user in users], since, window_days),
                "messages": self._daily_trend([message.created_at for message in messages], since, window_days),
                "challenge_completions": self._daily_trend([item.completed_at for item in challenge_completions], since, window_days),
                "vocabulary_words": self._daily_trend([item.created_at for item in vocabulary_entries], since, window_days),
            },
            api_consumption=self._api_consumption(messages),
            system_health=self._system_health(),
        )

    def _section(self, title: str, values: list[tuple[str, int | float | str, str]]) -> AdminAnalyticsSectionResponse:
        return AdminAnalyticsSectionResponse(
            title=title,
            metrics=[
                AdminMetricResponse(label=label, value=str(value), detail=detail)
                for label, value, detail in values
            ],
        )

    def _api_consumption(self, messages: list[Message]) -> AdminApiConsumptionResponse:
        saved_tokens = sum(message.token_count or 0 for message in messages)
        estimated_from_text = sum(max(1, len(message.content) // 4) for message in messages if not message.token_count)
        total_tokens = saved_tokens + estimated_from_text
        completion_tokens = sum(max(1, len(message.content) // 4) for message in messages if message.role == "assistant")
        prompt_tokens = max(0, total_tokens - completion_tokens)
        request_count = self.db.query(func.count(Message.id)).filter(Message.role == "user").scalar() or 0
        return AdminApiConsumptionResponse(
            estimated_total_tokens=total_tokens,
            estimated_prompt_tokens=prompt_tokens,
            estimated_completion_tokens=completion_tokens,
            estimated_requests=request_count,
            estimated_cost_usd=round((total_tokens / 1_000_000) * 0.60, 4),
            detail="Estimate uses saved token counts when available and falls back to roughly 4 characters per token.",
        )

    def _system_health(self) -> AdminSystemHealthResponse:
        settings = get_settings()
        table_counts = {
            "users": self.db.query(User).count(),
            "conversations": self.db.query(Conversation).count(),
            "messages": self.db.query(Message).count(),
            "challenge_completions": self.db.query(SpeakingChallengeCompletion).count(),
            "vocabulary_entries": self.db.query(VocabularyNotebookEntry).count(),
            "learning_issues": self.db.query(LearningIssue).count(),
        }
        return AdminSystemHealthResponse(
            status="ok",
            database_status="ok",
            environment=settings.environment,
            version=settings.app_version,
            table_counts=table_counts,
        )

    def _daily_trend(self, datetimes: list[datetime | None], since: datetime, window_days: int) -> list[AdminTrendPointResponse]:
        counts = Counter()
        for value in datetimes:
            if value is not None and self._in_window(value, since):
                counts[self._aware(value).date().isoformat()] += 1
        points = []
        now = datetime.now(timezone.utc)
        for offset in range(window_days - 1, -1, -1):
            day = (now - timedelta(days=offset)).date().isoformat()
            points.append(AdminTrendPointResponse(date=day, value=counts.get(day, 0)))
        return points

    def _distinct_challenge_learners(self, completions: list[SpeakingChallengeCompletion]) -> int:
        user_ids = {item.user_id for item in completions if item.user_id is not None}
        session_ids = {item.client_session_id for item in completions if item.user_id is None and item.client_session_id}
        return len(user_ids) + len(session_ids)

    def _average(self, numerator: int, denominator: int) -> float:
        return round(numerator / denominator, 1) if denominator else 0.0

    def _in_window(self, value: datetime | None, since: datetime) -> bool:
        return value is not None and self._aware(value) >= since

    def _aware(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
