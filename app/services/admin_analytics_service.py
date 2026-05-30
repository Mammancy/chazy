from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from time import monotonic

from sqlalchemy import case, distinct, func, select
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

_DASHBOARD_CACHE_TTL_SECONDS = 20
_dashboard_cache: dict[tuple[int], tuple[float, AdminAnalyticsDashboardResponse]] = {}


class AdminAnalyticsService:
    def __init__(self, db: Session):
        self.db = db

    def get_dashboard(self, window_days: int = 30) -> AdminAnalyticsDashboardResponse:
        window_days = max(1, min(window_days, 365))
        cache_key = (window_days,)
        cached = _dashboard_cache.get(cache_key)
        if cached and monotonic() - cached[0] < _DASHBOARD_CACHE_TTL_SECONDS:
            return cached[1]

        now = datetime.now(timezone.utc)
        since = now - timedelta(days=window_days)

        totals = self._table_totals(since)
        token_stats = self._token_stats()
        recent_user_messages = self._recent_user_message_rows(since)
        active_sessions = {
            metadata.get("session_id")
            for _, _, metadata in recent_user_messages
            if metadata and metadata.get("session_id")
        }
        active_user_count = self._count(Message.user_id, Message.role == "user", Message.created_at >= since, Message.user_id.is_not(None), distinct_values=True)
        recent_review_count = self._sum(VocabularyReviewSession.reviewed_count, VocabularyReviewSession.created_at >= since)

        response = AdminAnalyticsDashboardResponse(
            generated_at=now.isoformat(),
            window_days=window_days,
            user_growth=self._section(
                "User Growth",
                [
                    ("Total Users", totals["users"], f"{totals['recent_users']} new users in the last {window_days} days."),
                    ("Active Learners", active_user_count + len(active_sessions), "Distinct signed-in users plus anonymous sessions with recent messages."),
                    ("Active Accounts", totals["active_users"], "Accounts currently marked active."),
                ],
            ),
            engagement=self._section(
                "Engagement",
                [
                    ("Practice Messages", totals["user_messages"], f"{totals['recent_user_messages']} in the current window."),
                    ("Avg Messages/User", self._average(totals["messages"], max(totals["users"], 1)), "Total saved messages divided by registered users."),
                    ("Vocabulary Reviews", totals["vocabulary_reviews"], f"{recent_review_count} reviews in the current window."),
                ],
            ),
            conversation_volume=self._section(
                "Conversation Volume",
                [
                    ("Conversations", totals["conversations"], f"{totals['recent_conversations']} started in the last {window_days} days."),
                    ("Saved Messages", totals["messages"], f"{totals['assistant_messages']} assistant replies and {totals['user_messages']} learner messages."),
                    ("Avg Messages/Conversation", self._average(totals["messages"], max(totals["conversations"], 1)), "Conversation depth estimate from saved message count."),
                ],
            ),
            challenge_participation=self._section(
                "Challenge Participation",
                [
                    ("Completed Challenges", totals["challenge_completions"], f"{totals['recent_challenges']} completed in the current window."),
                    ("Challenge Learners", self._distinct_challenge_learners_count(), "Distinct users and anonymous sessions with challenge completions."),
                    ("Speaking Seconds", totals["speaking_seconds"], "Total reported speaking practice time."),
                ],
            ),
            learning_progress=self._section(
                "Learning Progress",
                [
                    ("Vocabulary Words", totals["vocabulary_entries"], f"{totals['recent_vocabulary']} saved in the current window."),
                    ("Mastered Words", totals["mastered_words"], "Words marked mastered in vocabulary notebooks."),
                    ("Tracked Issues", totals["learning_issues"], "Recurring grammar, vocabulary, and sentence structure issues tracked."),
                    ("Completed Assessments", totals["completed_assessments"], "Placement assessments completed by learners."),
                    ("Pronunciation Sessions", totals["completed_pronunciation_sessions"], "Completed pronunciation practice sessions."),
                ],
            ),
            learning_issue_categories=self._learning_issue_categories_sql(),
            conversation_analytics=self._conversation_analytics_sql(since, recent_user_messages, totals),
            trends={
                "new_users": self._daily_count_trend(User.created_at, since, window_days),
                "daily_active_users": self._daily_active_trend_rows(recent_user_messages, window_days),
                "messages": self._daily_count_trend(Message.created_at, since, window_days),
                "conversations": self._daily_count_trend(Conversation.created_at, since, window_days),
                "challenge_completions": self._daily_count_trend(SpeakingChallengeCompletion.completed_at, since, window_days),
                "vocabulary_words": self._daily_count_trend(VocabularyNotebookEntry.created_at, since, window_days),
                "fluency_score": self._daily_fluency_trend_rows(recent_user_messages, window_days),
            },
            api_consumption=self._api_consumption(token_stats),
            openai_usage=self._openai_usage(token_stats, since, window_days),
            system_health=self._system_health(totals),
        )
        _dashboard_cache[cache_key] = (monotonic(), response)
        return response

    def _section(self, title: str, values: list[tuple[str, int | float | str, str]]) -> AdminAnalyticsSectionResponse:
        return AdminAnalyticsSectionResponse(
            title=title,
            metrics=[
                AdminMetricResponse(label=label, value=str(value), detail=detail)
                for label, value, detail in values
            ],
        )

    def _count(self, column, *filters, distinct_values: bool = False) -> int:
        expression = func.count(distinct(column)) if distinct_values else func.count(column)
        statement = select(expression)
        if filters:
            statement = statement.where(*filters)
        return int(self.db.scalar(statement) or 0)

    def _sum(self, column, *filters) -> int:
        statement = select(func.coalesce(func.sum(column), 0))
        if filters:
            statement = statement.where(*filters)
        return int(self.db.scalar(statement) or 0)

    def _token_expression(self):
        return case(
            (Message.token_count.is_not(None), Message.token_count),
            else_=func.max(1, func.length(func.coalesce(Message.content, "")) / 4),
        )

    def _table_totals(self, since: datetime) -> dict[str, int]:
        return {
            "users": self._count(User.id),
            "recent_users": self._count(User.id, User.created_at >= since),
            "active_users": self._count(User.id, User.is_active.is_(True)),
            "messages": self._count(Message.id),
            "user_messages": self._count(Message.id, Message.role == "user"),
            "recent_user_messages": self._count(Message.id, Message.role == "user", Message.created_at >= since),
            "assistant_messages": self._count(Message.id, Message.role == "assistant"),
            "conversations": self._count(Conversation.id),
            "recent_conversations": self._count(Conversation.id, Conversation.created_at >= since),
            "challenge_completions": self._count(SpeakingChallengeCompletion.id),
            "recent_challenges": self._count(SpeakingChallengeCompletion.id, SpeakingChallengeCompletion.completed_at >= since),
            "speaking_seconds": self._sum(SpeakingChallengeCompletion.spoken_seconds),
            "vocabulary_entries": self._count(VocabularyNotebookEntry.id),
            "recent_vocabulary": self._count(VocabularyNotebookEntry.id, VocabularyNotebookEntry.created_at >= since),
            "mastered_words": self._count(VocabularyNotebookEntry.id, VocabularyNotebookEntry.mastery_status == "mastered"),
            "vocabulary_reviews": self._sum(VocabularyReviewSession.reviewed_count),
            "learning_issues": self._count(LearningIssue.id),
            "completed_assessments": self._count(PlacementAssessmentSession.id, PlacementAssessmentSession.status == "completed"),
            "completed_pronunciation_sessions": self._count(PronunciationPracticeSession.id, PronunciationPracticeSession.status == "completed"),
        }

    def _token_stats(self) -> dict[str, int]:
        token_expr = self._token_expression()
        row = self.db.execute(
            select(
                func.coalesce(func.sum(token_expr), 0),
                func.coalesce(func.sum(case((Message.role == "assistant", token_expr), else_=0)), 0),
                func.coalesce(func.sum(case((Message.role == "user", 1), else_=0)), 0),
            )
        ).one()
        return {
            "total_tokens": int(row[0] or 0),
            "completion_tokens": int(row[1] or 0),
            "request_count": int(row[2] or 0),
        }

    def _recent_user_message_rows(self, since: datetime) -> list[tuple[int | None, datetime, dict | None]]:
        return list(
            self.db.execute(
                select(Message.user_id, Message.created_at, Message.metadata_json)
                .where(Message.role == "user", Message.created_at >= since)
            ).all()
        )

    def _daily_count_trend(self, column, since: datetime, window_days: int) -> list[AdminTrendPointResponse]:
        rows = self.db.execute(
            select(func.date(column), func.count())
            .where(column >= since)
            .group_by(func.date(column))
        ).all()
        counts = {str(day): int(count or 0) for day, count in rows if day}
        return self._trend_points(counts, window_days)

    def _daily_token_counts(self, since: datetime) -> Counter:
        token_expr = self._token_expression()
        rows = self.db.execute(
            select(func.date(Message.created_at), func.coalesce(func.sum(token_expr), 0))
            .where(Message.created_at >= since)
            .group_by(func.date(Message.created_at))
        ).all()
        return Counter({str(day): int(value or 0) for day, value in rows if day})

    def _daily_request_counts(self, since: datetime) -> Counter:
        rows = self.db.execute(
            select(func.date(Message.created_at), func.count(Message.id))
            .where(Message.created_at >= since, Message.role == "user")
            .group_by(func.date(Message.created_at))
        ).all()
        return Counter({str(day): int(value or 0) for day, value in rows if day})

    def _trend_points(self, counts: dict[str, int] | Counter, window_days: int) -> list[AdminTrendPointResponse]:
        points = []
        now = datetime.now(timezone.utc)
        for offset in range(window_days - 1, -1, -1):
            day = (now - timedelta(days=offset)).date().isoformat()
            points.append(AdminTrendPointResponse(date=day, value=int(counts.get(day, 0))))
        return points

    def _daily_active_trend_rows(
        self,
        messages: list[tuple[int | None, datetime, dict | None]],
        window_days: int,
    ) -> list[AdminTrendPointResponse]:
        active_by_day: dict[str, set[str]] = {}
        for index, (user_id, created_at, metadata) in enumerate(messages):
            day = self._aware(created_at).date().isoformat()
            if user_id is not None:
                identity = f"user:{user_id}"
            else:
                session_id = (metadata or {}).get("session_id")
                identity = f"session:{session_id}" if session_id else f"message:{index}"
            active_by_day.setdefault(day, set()).add(identity)
        return self._trend_points({day: len(values) for day, values in active_by_day.items()}, window_days)

    def _daily_fluency_trend_rows(
        self,
        messages: list[tuple[int | None, datetime, dict | None]],
        window_days: int,
    ) -> list[AdminTrendPointResponse]:
        scores_by_day: dict[str, list[int]] = {}
        for _, created_at, metadata in messages:
            score = (metadata or {}).get("fluency_score")
            if not isinstance(score, int | float):
                continue
            day = self._aware(created_at).date().isoformat()
            scores_by_day.setdefault(day, []).append(round(score))
        averages = {
            day: round(sum(scores) / len(scores))
            for day, scores in scores_by_day.items()
            if scores
        }
        return self._trend_points(averages, window_days)

    def _learning_issue_categories_sql(self) -> list[AdminCategoryCountResponse]:
        rows = self.db.execute(
            select(
                func.coalesce(LearningIssue.category, "uncategorized"),
                func.coalesce(func.sum(LearningIssue.count), 0),
            )
            .group_by(LearningIssue.category)
            .order_by(func.coalesce(func.sum(LearningIssue.count), 0).desc())
        ).all()
        return [
            AdminCategoryCountResponse(category=str(category), count=int(count or 0))
            for category, count in rows
        ]

    def _distinct_challenge_learners_count(self) -> int:
        user_count = self._count(
            SpeakingChallengeCompletion.user_id,
            SpeakingChallengeCompletion.user_id.is_not(None),
            distinct_values=True,
        )
        session_count = self._count(
            SpeakingChallengeCompletion.client_session_id,
            SpeakingChallengeCompletion.user_id.is_(None),
            SpeakingChallengeCompletion.client_session_id.is_not(None),
            distinct_values=True,
        )
        return user_count + session_count

    def _conversation_analytics_sql(
        self,
        since: datetime,
        recent_user_messages: list[tuple[int | None, datetime, dict | None]],
        totals: dict[str, int],
    ) -> AdminConversationAnalyticsResponse:
        duration_rows = self.db.execute(
            select(
                Message.conversation_id,
                func.min(Message.created_at),
                func.max(Message.created_at),
                func.count(Message.id),
            )
            .where(Message.conversation_id.is_not(None))
            .group_by(Message.conversation_id)
            .having(func.count(Message.id) >= 2)
        ).all()
        durations = [
            max(0, (self._aware(last_seen) - self._aware(first_seen)).total_seconds() / 60)
            for _, first_seen, last_seen, _ in duration_rows
            if first_seen and last_seen
        ]

        feature_counts = Counter()
        hour_counts = Counter()
        for _, created_at, metadata in recent_user_messages:
            feature = (metadata or {}).get("practice_mode") or (metadata or {}).get("mode") or "chat"
            feature_counts[str(feature)] += 1
            hour_counts[str(self._aware(created_at).hour).zfill(2)] += 1

        active_days = self._count(
            distinct(func.date(Conversation.created_at)),
            Conversation.created_at >= since,
        )
        engagement_by_hour = [
            AdminTrendPointResponse(date=f"{hour:02d}:00", value=hour_counts.get(f"{hour:02d}", 0))
            for hour in range(24)
        ]
        return AdminConversationAnalyticsResponse(
            average_session_duration_minutes=round(sum(durations) / len(durations), 1) if durations else 0.0,
            median_session_duration_minutes=self._median(durations),
            average_messages_per_conversation=self._average(totals["messages"], max(totals["conversations"], 1)),
            active_conversation_days=active_days,
            feature_usage=[
                AdminCategoryCountResponse(category=category, count=count)
                for category, count in feature_counts.most_common()
            ],
            engagement_by_hour=engagement_by_hour,
        )

    def _user_usage_sql(self) -> list[AdminUserUsageResponse]:
        token_expr = self._token_expression()
        rows = self.db.execute(
            select(
                Message.user_id,
                Message.metadata_json,
                func.coalesce(func.sum(token_expr), 0),
                func.coalesce(func.sum(case((Message.role == "user", 1), else_=0)), 0),
                func.max(Message.created_at),
            )
            .group_by(Message.user_id, Message.metadata_json)
        ).all()
        usage: dict[str, dict] = {}
        for user_id, metadata, estimated_tokens, request_count, last_seen_at in rows:
            if user_id is not None:
                identity = f"user:{user_id}"
                display_name = f"User {user_id}"
            else:
                session_id = (metadata or {}).get("session_id")
                identity = f"session:{session_id}" if session_id else "anonymous"
                display_name = f"Session {session_id}" if session_id else "Anonymous"
            record = usage.setdefault(
                identity,
                {
                    "display_name": display_name,
                    "request_count": 0,
                    "estimated_tokens": 0,
                    "last_seen_at": None,
                },
            )
            record["request_count"] += int(request_count or 0)
            record["estimated_tokens"] += int(estimated_tokens or 0)
            if last_seen_at and (
                record["last_seen_at"] is None
                or self._aware(last_seen_at) > self._aware(record["last_seen_at"])
            ):
                record["last_seen_at"] = last_seen_at

        return sorted(
            [
                AdminUserUsageResponse(
                    identity=identity,
                    display_name=record["display_name"],
                    request_count=record["request_count"],
                    estimated_tokens=record["estimated_tokens"],
                    estimated_cost_usd=round((record["estimated_tokens"] / 1_000_000) * 0.60, 4),
                    last_seen_at=self._aware(record["last_seen_at"]).isoformat() if record["last_seen_at"] else None,
                )
                for identity, record in usage.items()
            ],
            key=lambda item: item.estimated_tokens,
            reverse=True,
        )[:25]

    def _api_consumption(self, token_stats: dict[str, int]) -> AdminApiConsumptionResponse:
        total_tokens = token_stats["total_tokens"]
        completion_tokens = token_stats["completion_tokens"]
        prompt_tokens = max(0, total_tokens - completion_tokens)
        request_count = token_stats["request_count"]
        return AdminApiConsumptionResponse(
            estimated_total_tokens=total_tokens,
            estimated_prompt_tokens=prompt_tokens,
            estimated_completion_tokens=completion_tokens,
            estimated_requests=request_count,
            estimated_cost_usd=round((total_tokens / 1_000_000) * 0.60, 4),
            detail="Estimate uses saved token counts when available and falls back to roughly 4 characters per token.",
        )

    def _openai_usage(self, token_stats: dict[str, int], since: datetime, window_days: int) -> AdminOpenAIUsageResponse:
        total_tokens = token_stats["total_tokens"]
        completion_tokens = token_stats["completion_tokens"]
        prompt_tokens = max(0, total_tokens - completion_tokens)
        request_count = token_stats["request_count"]

        token_counts = self._daily_token_counts(since)
        request_counts = self._daily_request_counts(since)

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
            user_usage=self._user_usage_sql(),
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

    def _system_health(self, totals: dict[str, int] | None = None) -> AdminSystemHealthResponse:
        settings = get_settings()
        totals = totals or self._table_totals(datetime.now(timezone.utc))
        table_counts = {
            "users": totals["users"],
            "conversations": totals["conversations"],
            "messages": totals["messages"],
            "challenge_completions": totals["challenge_completions"],
            "vocabulary_entries": totals["vocabulary_entries"],
            "learning_issues": totals["learning_issues"],
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
