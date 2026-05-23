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
    AdminCategoryCountResponse,
    AdminConversationAnalyticsResponse,
    AdminMetricResponse,
    AdminOpenAIUsageResponse,
    AdminSystemHealthResponse,
    AdminTrendPointResponse,
    AdminUserUsageResponse,
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
            learning_issue_categories=self._learning_issue_categories(learning_issues),
            conversation_analytics=self._conversation_analytics(conversations, messages, since),
            trends={
                "new_users": self._daily_trend([user.created_at for user in users], since, window_days),
                "daily_active_users": self._daily_active_trend(recent_messages, since, window_days),
                "messages": self._daily_trend([message.created_at for message in messages], since, window_days),
                "conversations": self._daily_trend([conversation.created_at for conversation in conversations], since, window_days),
                "challenge_completions": self._daily_trend([item.completed_at for item in challenge_completions], since, window_days),
                "vocabulary_words": self._daily_trend([item.created_at for item in vocabulary_entries], since, window_days),
                "fluency_score": self._daily_fluency_trend(messages, since, window_days),
            },
            api_consumption=self._api_consumption(messages),
            openai_usage=self._openai_usage(messages, since, window_days),
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
        total_tokens = sum(self._message_token_estimate(message) for message in messages)
        completion_tokens = sum(self._message_token_estimate(message) for message in messages if message.role == "assistant")
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

    def _openai_usage(self, messages: list[Message], since: datetime, window_days: int) -> AdminOpenAIUsageResponse:
        user_messages = [message for message in messages if message.role == "user"]
        assistant_messages = [message for message in messages if message.role == "assistant"]
        total_tokens = sum(self._message_token_estimate(message) for message in messages)
        completion_tokens = sum(self._message_token_estimate(message) for message in assistant_messages)
        prompt_tokens = max(0, total_tokens - completion_tokens)
        request_count = len(user_messages)

        token_counts = Counter()
        request_counts = Counter()
        for message in messages:
            if self._in_window(message.created_at, since):
                day = self._aware(message.created_at).date().isoformat()
                token_counts[day] += self._message_token_estimate(message)
                if message.role == "user":
                    request_counts[day] += 1

        token_trend = []
        request_trend = []
        cost_trend = []
        now = datetime.now(timezone.utc)
        for offset in range(window_days - 1, -1, -1):
            day = (now - timedelta(days=offset)).date().isoformat()
            tokens = token_counts.get(day, 0)
            requests = request_counts.get(day, 0)
            token_trend.append(AdminTrendPointResponse(date=day, value=tokens))
            request_trend.append(AdminTrendPointResponse(date=day, value=requests))
            cost_trend.append(AdminTrendPointResponse(date=day, value=round((tokens / 1_000_000) * 60)))

        return AdminOpenAIUsageResponse(
            total_tokens=total_tokens,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            request_count=request_count,
            average_tokens_per_request=round(total_tokens / request_count, 1) if request_count else 0.0,
            estimated_cost_usd=round((total_tokens / 1_000_000) * 0.60, 4),
            token_trend=token_trend,
            request_trend=request_trend,
            cost_trend=cost_trend,
            user_usage=self._user_usage(messages),
            detail="OpenAI usage is estimated from saved Chazy message token counts; missing token counts use a 4-characters-per-token fallback.",
        )

    def _user_usage(self, messages: list[Message]) -> list[AdminUserUsageResponse]:
        usage: dict[str, dict] = {}
        for message in messages:
            identity, display_name = self._usage_identity(message)
            record = usage.setdefault(
                identity,
                {
                    "display_name": display_name,
                    "request_count": 0,
                    "estimated_tokens": 0,
                    "last_seen_at": None,
                },
            )
            record["estimated_tokens"] += self._message_token_estimate(message)
            if message.role == "user":
                record["request_count"] += 1
            current_seen = self._aware(message.created_at)
            if record["last_seen_at"] is None or current_seen > record["last_seen_at"]:
                record["last_seen_at"] = current_seen

        rows = []
        for identity, record in usage.items():
            rows.append(
                AdminUserUsageResponse(
                    identity=identity,
                    display_name=record["display_name"],
                    request_count=record["request_count"],
                    estimated_tokens=record["estimated_tokens"],
                    estimated_cost_usd=round((record["estimated_tokens"] / 1_000_000) * 0.60, 4),
                    last_seen_at=record["last_seen_at"].isoformat() if record["last_seen_at"] else None,
                )
            )
        return sorted(rows, key=lambda item: item.estimated_tokens, reverse=True)[:25]

    def _usage_identity(self, message: Message) -> tuple[str, str]:
        if message.user_id is not None:
            return f"user:{message.user_id}", f"User {message.user_id}"
        metadata = message.metadata_json or {}
        session_id = metadata.get("session_id")
        if session_id:
            return f"session:{session_id}", f"Session {session_id}"
        return "anonymous", "Anonymous"

    def _message_token_estimate(self, message: Message) -> int:
        if message.token_count:
            return message.token_count
        return max(1, len(message.content or "") // 4)

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

    def _daily_active_trend(self, messages: list[Message], since: datetime, window_days: int) -> list[AdminTrendPointResponse]:
        active_by_day: dict[str, set[str]] = {}
        for message in messages:
            if message.role != "user" or not self._in_window(message.created_at, since):
                continue
            day = self._aware(message.created_at).date().isoformat()
            identity = f"user:{message.user_id}" if message.user_id is not None else None
            if identity is None:
                metadata = message.metadata_json or {}
                session_id = metadata.get("session_id")
                identity = f"session:{session_id}" if session_id else f"message:{message.id}"
            active_by_day.setdefault(day, set()).add(identity)

        points = []
        now = datetime.now(timezone.utc)
        for offset in range(window_days - 1, -1, -1):
            day = (now - timedelta(days=offset)).date().isoformat()
            points.append(AdminTrendPointResponse(date=day, value=len(active_by_day.get(day, set()))))
        return points

    def _daily_fluency_trend(self, messages: list[Message], since: datetime, window_days: int) -> list[AdminTrendPointResponse]:
        scores_by_day: dict[str, list[int]] = {}
        for message in messages:
            if message.role != "user" or not self._in_window(message.created_at, since):
                continue
            metadata = message.metadata_json or {}
            score = metadata.get("fluency_score")
            if not isinstance(score, int | float):
                continue
            day = self._aware(message.created_at).date().isoformat()
            scores_by_day.setdefault(day, []).append(round(score))

        points = []
        now = datetime.now(timezone.utc)
        for offset in range(window_days - 1, -1, -1):
            day = (now - timedelta(days=offset)).date().isoformat()
            scores = scores_by_day.get(day, [])
            average_score = round(sum(scores) / len(scores)) if scores else 0
            points.append(AdminTrendPointResponse(date=day, value=average_score))
        return points

    def _learning_issue_categories(self, issues: list[LearningIssue]) -> list[AdminCategoryCountResponse]:
        counts = Counter()
        for issue in issues:
            counts[issue.category or "uncategorized"] += issue.count or 1
        return [
            AdminCategoryCountResponse(category=category, count=count)
            for category, count in counts.most_common()
        ]

    def _conversation_analytics(
        self,
        conversations: list[Conversation],
        messages: list[Message],
        since: datetime,
    ) -> AdminConversationAnalyticsResponse:
        messages_by_conversation: dict[int, list[Message]] = {}
        for message in messages:
            messages_by_conversation.setdefault(message.conversation_id, []).append(message)

        durations: list[float] = []
        for conversation_id, conversation_messages in messages_by_conversation.items():
            if conversation_id is None or len(conversation_messages) < 2:
                continue
            ordered = sorted(conversation_messages, key=lambda item: self._aware(item.created_at))
            duration_seconds = (
                self._aware(ordered[-1].created_at) - self._aware(ordered[0].created_at)
            ).total_seconds()
            durations.append(max(0, duration_seconds / 60))

        recent_user_messages = [
            message
            for message in messages
            if message.role == "user" and self._in_window(message.created_at, since)
        ]
        feature_counts = Counter()
        hour_counts = Counter()
        for message in recent_user_messages:
            metadata = message.metadata_json or {}
            feature = metadata.get("practice_mode") or metadata.get("mode") or "chat"
            feature_counts[str(feature)] += 1
            hour_counts[str(self._aware(message.created_at).hour).zfill(2)] += 1

        engagement_by_hour = [
            AdminTrendPointResponse(date=f"{hour:02d}:00", value=hour_counts.get(f"{hour:02d}", 0))
            for hour in range(24)
        ]
        active_days = {
            self._aware(conversation.created_at).date().isoformat()
            for conversation in conversations
            if self._in_window(conversation.created_at, since)
        }
        return AdminConversationAnalyticsResponse(
            average_session_duration_minutes=round(sum(durations) / len(durations), 1) if durations else 0.0,
            median_session_duration_minutes=self._median(durations),
            average_messages_per_conversation=self._average(len(messages), max(len(conversations), 1)),
            active_conversation_days=len(active_days),
            feature_usage=[
                AdminCategoryCountResponse(category=category, count=count)
                for category, count in feature_counts.most_common()
            ],
            engagement_by_hour=engagement_by_hour,
        )

    def _distinct_challenge_learners(self, completions: list[SpeakingChallengeCompletion]) -> int:
        user_ids = {item.user_id for item in completions if item.user_id is not None}
        session_ids = {item.client_session_id for item in completions if item.user_id is None and item.client_session_id}
        return len(user_ids) + len(session_ids)

    def _average(self, numerator: int, denominator: int) -> float:
        return round(numerator / denominator, 1) if denominator else 0.0

    def _median(self, values: list[float]) -> float:
        if not values:
            return 0.0
        sorted_values = sorted(values)
        midpoint = len(sorted_values) // 2
        if len(sorted_values) % 2:
            return round(sorted_values[midpoint], 1)
        return round((sorted_values[midpoint - 1] + sorted_values[midpoint]) / 2, 1)

    def _in_window(self, value: datetime | None, since: datetime) -> bool:
        return value is not None and self._aware(value) >= since

    def _aware(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
