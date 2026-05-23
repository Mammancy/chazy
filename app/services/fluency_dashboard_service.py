from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.learning_analytics import LearningIssue
from app.models.message import Message
from app.schemas.fluency_dashboard import (
    DashboardInsightResponse,
    DashboardMetricResponse,
    FluencyDashboardResponse,
)
from app.services.learning_analytics_service import LearningAnalyticsService
from app.services.speaking_challenge_service import SpeakingChallengeService


class FluencyDashboardService:
    def __init__(self, db: Session):
        self.db = db

    def get_dashboard(self, session_id: str, user_id: int | None = None) -> FluencyDashboardResponse:
        messages = self._user_messages(session_id=session_id, user_id=user_id)
        issues = self._issues(session_id=session_id, user_id=user_id)
        analytics = LearningAnalyticsService(self.db).get_analytics(session_id=session_id, user_id=user_id)
        streak = SpeakingChallengeService(self.db).get_streak(session_id=session_id, user_id=user_id)

        grammar_issue_count = sum(issue.count for issue in issues if issue.category == "grammar")
        vocabulary_issue_count = sum(issue.count for issue in issues if issue.category == "vocabulary")
        vocabulary_suggestions = self._unique_vocabulary_suggestions(messages)
        completed_conversation_count = self._conversation_count(session_id=session_id, user_id=user_id)

        return FluencyDashboardResponse(
            session_id=session_id,
            user_id=user_id,
            grammar_progress=DashboardMetricResponse(
                label="Grammar Progress",
                value=self._grammar_value(grammar_issue_count, len(messages)),
                detail=f"{grammar_issue_count} grammar patterns tracked across {len(messages)} practice messages.",
            ),
            vocabulary_growth=DashboardMetricResponse(
                label="Vocabulary Growth",
                value=str(len(vocabulary_suggestions)),
                detail=f"{len(vocabulary_suggestions)} vocabulary suggestions collected from coaching history.",
            ),
            completed_conversations=DashboardMetricResponse(
                label="Completed Conversations",
                value=str(completed_conversation_count),
                detail="Conversation threads with saved learner messages.",
            ),
            challenge_streak=DashboardMetricResponse(
                label="Challenge Streak",
                value=f"{streak.current_streak} days",
                detail=f"Longest streak: {streak.longest_streak} days.",
            ),
            personalized_insights=self._insights(
                grammar_issue_count=grammar_issue_count,
                vocabulary_issue_count=vocabulary_issue_count,
                recommendation_source=analytics.recommendations,
                streak_days=streak.current_streak,
            ),
        )

    def _user_messages(self, *, session_id: str, user_id: int | None) -> list[Message]:
        query = select(Message).where(Message.role == "user")
        if user_id is not None:
            query = query.where(Message.user_id == user_id)
        else:
            query = query.where(Message.metadata_json["session_id"].as_string() == session_id)
        return list(self.db.scalars(query.order_by(Message.created_at.asc())).all())

    def _issues(self, *, session_id: str, user_id: int | None) -> list[LearningIssue]:
        query = select(LearningIssue).where(LearningIssue.session_id == session_id)
        if user_id is not None:
            query = query.where(LearningIssue.user_id == user_id)
        return list(self.db.scalars(query).all())

    def _conversation_count(self, *, session_id: str, user_id: int | None) -> int:
        if user_id is None:
            return self.db.query(Message.conversation_id).filter(
                Message.role == "user",
                Message.metadata_json["session_id"].as_string() == session_id,
            ).distinct().count()
        return self.db.query(Conversation).filter(Conversation.user_id == user_id).count()

    def _unique_vocabulary_suggestions(self, messages: list[Message]) -> set[str]:
        suggestions = set()
        for message in messages:
            metadata = message.metadata_json or {}
            for suggestion in metadata.get("vocabulary_suggestions") or []:
                if isinstance(suggestion, str) and suggestion.strip():
                    suggestions.add(suggestion.strip().lower())
        return suggestions

    def _grammar_value(self, grammar_issue_count: int, message_count: int) -> str:
        if message_count == 0:
            return "No data"
        ratio = max(0, 100 - round((grammar_issue_count / max(message_count, 1)) * 10))
        return f"{ratio}%"

    def _insights(
        self,
        *,
        grammar_issue_count: int,
        vocabulary_issue_count: int,
        recommendation_source,
        streak_days: int,
    ) -> list[DashboardInsightResponse]:
        insights = [
            DashboardInsightResponse(
                title=item.title,
                body=item.description,
                category=item.category,
            )
            for item in recommendation_source[:4]
        ]
        if streak_days > 0:
            insights.append(
                DashboardInsightResponse(
                    title="Keep Your Speaking Rhythm",
                    body=f"You have a {streak_days}-day challenge streak. Complete one prompt today to protect it.",
                    category="challenge",
                )
            )
        if grammar_issue_count == 0 and vocabulary_issue_count == 0:
            insights.append(
                DashboardInsightResponse(
                    title="Start With More Practice Data",
                    body="Send more chat messages and complete speaking challenges so Chazy can personalize this dashboard.",
                    category="general",
                )
            )
        return insights[:6]
