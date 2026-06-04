from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.achievement import AchievementAward
from app.models.conversation import Conversation
from app.models.conversation_scenario import ConversationScenarioSession
from app.models.message import Message
from app.models.placement_assessment import PlacementAssessmentSession
from app.models.practice_session import PracticeSession
from app.models.pronunciation import PronunciationPracticeSession
from app.schemas.achievement import (
    AchievementAwardResponse,
    AchievementProgressResponse,
    AchievementSummaryResponse,
)
from app.services.speaking_challenge_service import SpeakingChallengeService
from app.services.lesson_service import LessonService
from app.services.vocabulary_notebook_service import VocabularyNotebookService


@dataclass(frozen=True)
class AchievementDefinition:
    key: str
    category: str
    title: str
    description: str
    signal: str
    target: int
    points: int


ACHIEVEMENT_CATALOG = [
    AchievementDefinition("streak_1", "streak", "First Streak", "Complete a daily speaking challenge.", "challenge_streak", 1, 10),
    AchievementDefinition("streak_3", "streak", "Three-Day Voice", "Keep a daily speaking challenge streak for 3 days.", "challenge_streak", 3, 25),
    AchievementDefinition("streak_7", "streak", "Weekly Speaker", "Keep a daily speaking challenge streak for 7 days.", "challenge_streak", 7, 50),
    AchievementDefinition("vocab_1", "vocabulary", "First Word Saved", "Save your first word in the vocabulary notebook.", "total_words", 1, 10),
    AchievementDefinition("vocab_10", "vocabulary", "Vocabulary Builder", "Save 10 words in the vocabulary notebook.", "total_words", 10, 30),
    AchievementDefinition("vocab_master_5", "vocabulary", "Mastery Starter", "Master 5 saved vocabulary words.", "mastered_words", 5, 40),
    AchievementDefinition("vocab_reviews_10", "vocabulary", "Review Habit", "Complete 10 vocabulary reviews.", "total_reviews", 10, 35),
    AchievementDefinition("conversation_1", "conversation", "First Conversation", "Start your first English practice conversation.", "conversation_count", 1, 10),
    AchievementDefinition("conversation_5", "conversation", "Conversation Builder", "Complete 5 conversation threads.", "conversation_count", 5, 30),
    AchievementDefinition("scenario_1", "conversation", "Role-Play Starter", "Complete one guided role-play scenario.", "completed_scenarios", 1, 25),
    AchievementDefinition("pronunciation_1", "pronunciation", "Pronunciation Starter", "Complete one pronunciation practice session.", "pronunciation_sessions", 1, 20),
    AchievementDefinition("assessment_complete", "milestone", "Level Check Complete", "Complete an English placement assessment.", "completed_assessments", 1, 30),
    AchievementDefinition("lesson_1", "lesson", "Lesson Starter", "Complete your first lesson.", "completed_lessons", 1, 20),
    AchievementDefinition("lesson_5", "lesson", "Lesson Builder", "Complete five lessons.", "completed_lessons", 5, 60),
    AchievementDefinition("partner_practice_1", "practice_session", "Human Practice Starter", "Complete one scheduled partner practice session.", "completed_practice_sessions", 1, 20),
    AchievementDefinition("partner_practice_5", "practice_session", "Conversation Partner", "Complete five scheduled partner practice sessions.", "completed_practice_sessions", 5, 60),
    AchievementDefinition("practice_messages_10", "consistency", "Practice Consistency", "Send 10 learner messages to Chazy.", "practice_messages", 10, 25),
    AchievementDefinition("practice_messages_50", "consistency", "Steady Learner", "Send 50 learner messages to Chazy.", "practice_messages", 50, 60),
]


class AchievementService:
    def __init__(self, db: Session):
        self.db = db

    def evaluate(self, *, session_id: str, user_id: int | None = None) -> AchievementSummaryResponse:
        signals = self._signals(session_id=session_id, user_id=user_id)
        newly_awarded: list[AchievementAward] = []

        for definition in ACHIEVEMENT_CATALOG:
            current_value = signals.get(definition.signal, 0)
            if current_value < definition.target:
                continue
            if self._existing_award(session_id=session_id, user_id=user_id, achievement_key=definition.key):
                continue
            award = AchievementAward(
                session_id=session_id,
                user_id=user_id,
                achievement_key=definition.key,
                category=definition.category,
                title=definition.title,
                description=definition.description,
                points=definition.points,
                metadata_json={
                    "signal": definition.signal,
                    "current_value": current_value,
                    "target_value": definition.target,
                },
            )
            self.db.add(award)
            newly_awarded.append(award)

        if newly_awarded:
            self.db.commit()
            for award in newly_awarded:
                self.db.refresh(award)

        return self.summary(session_id=session_id, user_id=user_id, signals=signals, newly_awarded=newly_awarded)

    def summary(
        self,
        *,
        session_id: str,
        user_id: int | None = None,
        signals: dict[str, int] | None = None,
        newly_awarded: list[AchievementAward] | None = None,
    ) -> AchievementSummaryResponse:
        awards = self._awards(session_id=session_id, user_id=user_id)
        badges_by_category: dict[str, int] = {}
        for award in awards:
            badges_by_category[award.category] = badges_by_category.get(award.category, 0) + 1

        awarded_keys = {award.achievement_key for award in awards}
        computed_signals = signals or self._signals(session_id=session_id, user_id=user_id)
        next_milestones = [
            AchievementProgressResponse(
                achievement_key=definition.key,
                category=definition.category,
                title=definition.title,
                description=definition.description,
                current_value=computed_signals.get(definition.signal, 0),
                target_value=definition.target,
                completed=False,
                points=definition.points,
            )
            for definition in ACHIEVEMENT_CATALOG
            if definition.key not in awarded_keys
        ]
        next_milestones.sort(key=lambda item: (item.target_value - item.current_value, item.target_value))

        return AchievementSummaryResponse(
            session_id=session_id,
            user_id=user_id,
            total_points=sum(award.points for award in awards),
            awarded_count=len(awards),
            badges_by_category=badges_by_category,
            recent_awards=[AchievementAwardResponse.model_validate(award) for award in awards[:8]],
            next_milestones=next_milestones[:6],
            newly_awarded=[AchievementAwardResponse.model_validate(award) for award in newly_awarded or []],
        )

    def _signals(self, *, session_id: str, user_id: int | None) -> dict[str, int]:
        streak = SpeakingChallengeService(self.db).get_streak(session_id=session_id, user_id=user_id)
        vocabulary_stats = VocabularyNotebookService(self.db).stats(session_id=session_id, user_id=user_id)
        return {
            "challenge_streak": streak.current_streak,
            "total_words": vocabulary_stats.total_words,
            "mastered_words": vocabulary_stats.mastered_words,
            "total_reviews": vocabulary_stats.total_reviews,
            "conversation_count": self._conversation_count(session_id=session_id, user_id=user_id),
            "completed_scenarios": self._completed_scenarios(session_id=session_id, user_id=user_id),
            "pronunciation_sessions": self._pronunciation_sessions(session_id=session_id, user_id=user_id),
            "completed_assessments": self._completed_assessments(session_id=session_id, user_id=user_id),
            "completed_lessons": LessonService(self.db).completed_count(user_id=user_id),
            "completed_practice_sessions": self._completed_practice_sessions(user_id=user_id),
            "practice_messages": self._practice_messages(session_id=session_id, user_id=user_id),
        }

    def _awards(self, *, session_id: str, user_id: int | None) -> list[AchievementAward]:
        query = select(AchievementAward).where(AchievementAward.session_id == session_id)
        if user_id is not None:
            query = query.where(AchievementAward.user_id == user_id)
        else:
            query = query.where(AchievementAward.user_id.is_(None))
        return list(self.db.scalars(query.order_by(AchievementAward.awarded_at.desc(), AchievementAward.id.desc())).all())

    def _existing_award(self, *, session_id: str, user_id: int | None, achievement_key: str) -> AchievementAward | None:
        query = select(AchievementAward).where(
            AchievementAward.session_id == session_id,
            AchievementAward.achievement_key == achievement_key,
        )
        if user_id is not None:
            query = query.where(AchievementAward.user_id == user_id)
        else:
            query = query.where(AchievementAward.user_id.is_(None))
        return self.db.scalar(query.limit(1))

    def _conversation_count(self, *, session_id: str, user_id: int | None) -> int:
        if user_id is not None:
            return self.db.query(Conversation).filter(Conversation.user_id == user_id).count()
        return self.db.query(Message.conversation_id).filter(
            Message.role == "user",
            Message.metadata_json["session_id"].as_string() == session_id,
        ).distinct().count()

    def _practice_messages(self, *, session_id: str, user_id: int | None) -> int:
        query = self.db.query(Message).filter(Message.role == "user")
        if user_id is not None:
            query = query.filter(Message.user_id == user_id)
        else:
            query = query.filter(Message.metadata_json["session_id"].as_string() == session_id)
        return query.count()

    def _completed_scenarios(self, *, session_id: str, user_id: int | None) -> int:
        query = self.db.query(ConversationScenarioSession).filter(
            ConversationScenarioSession.status == "completed",
            ConversationScenarioSession.session_id == session_id,
        )
        if user_id is not None:
            query = query.filter(ConversationScenarioSession.user_id == user_id)
        return query.count()

    def _pronunciation_sessions(self, *, session_id: str, user_id: int | None) -> int:
        query = self.db.query(PronunciationPracticeSession).filter(
            PronunciationPracticeSession.status == "completed",
            PronunciationPracticeSession.client_session_id == session_id,
        )
        if user_id is not None:
            query = query.filter(PronunciationPracticeSession.user_id == user_id)
        return query.count()

    def _completed_assessments(self, *, session_id: str, user_id: int | None) -> int:
        query = self.db.query(PlacementAssessmentSession).filter(
            PlacementAssessmentSession.status == "completed",
            PlacementAssessmentSession.session_id == session_id,
        )
        if user_id is not None:
            query = query.filter(PlacementAssessmentSession.user_id == user_id)
        return query.count()

    def _completed_practice_sessions(self, *, user_id: int | None) -> int:
        if user_id is None:
            return 0
        return self.db.query(PracticeSession).filter(
            PracticeSession.status == "completed",
            (
                (PracticeSession.requester_user_id == user_id)
                | (PracticeSession.partner_user_id == user_id)
            ),
        ).count()
