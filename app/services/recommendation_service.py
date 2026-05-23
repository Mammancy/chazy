from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.learning_analytics import LearningIssue
from app.models.message import Message
from app.models.speaking_challenge import SpeakingChallengeCompletion
from app.models.user import User
from app.schemas.recommendation import (
    PersonalizedRecommendationResponse,
    RecommendationItemResponse,
    RecommendationSignalResponse,
    TargetedPracticeTopicResponse,
)


class RecommendationService:
    """Generates deterministic personalized Chazy practice recommendations."""

    def __init__(self, db: Session):
        self.db = db

    def get_recommendations(self, session_id: str, user_id: int | None = None) -> PersonalizedRecommendationResponse:
        user = self.db.get(User, user_id) if user_id is not None else None
        issues = self._issues(session_id=session_id, user_id=user_id)
        messages = self._messages(session_id=session_id, user_id=user_id)
        learning_goals = self._learning_goals(user=user, messages=messages)
        completed_challenges = self._completed_challenge_count(session_id=session_id, user_id=user_id)
        average_fluency_score = self._average_fluency_score(messages)
        conversation_count = self._conversation_count(session_id=session_id, user_id=user_id)

        daily = self._daily_recommendations(
            issues=issues,
            completed_challenges=completed_challenges,
            average_fluency_score=average_fluency_score,
            learning_goals=learning_goals,
        )
        topics = self._targeted_topics(issues=issues, learning_goals=learning_goals)
        improvements = self._improvement_suggestions(
            issues=issues,
            average_fluency_score=average_fluency_score,
            conversation_count=conversation_count,
        )

        return PersonalizedRecommendationResponse(
            session_id=session_id,
            user_id=user_id,
            daily_recommendations=daily,
            targeted_practice_topics=topics,
            improvement_suggestions=improvements,
            signals=RecommendationSignalResponse(
                mistake_count=sum(issue.count for issue in issues),
                completed_challenges=completed_challenges,
                average_fluency_score=average_fluency_score,
                conversation_count=conversation_count,
                learning_goals=learning_goals,
            ),
        )

    def _issues(self, *, session_id: str, user_id: int | None) -> list[LearningIssue]:
        query = select(LearningIssue).where(LearningIssue.session_id == session_id)
        if user_id is not None:
            query = query.where(LearningIssue.user_id == user_id)
        return list(self.db.scalars(query.order_by(LearningIssue.count.desc(), LearningIssue.last_seen_at.desc())).all())

    def _messages(self, *, session_id: str, user_id: int | None) -> list[Message]:
        query = select(Message).where(Message.role == "user")
        if user_id is not None:
            query = query.where(Message.user_id == user_id)
        else:
            query = query.where(Message.metadata_json["session_id"].as_string() == session_id)
        return list(self.db.scalars(query.order_by(Message.created_at.desc())).all())

    def _completed_challenge_count(self, *, session_id: str, user_id: int | None) -> int:
        query = self.db.query(SpeakingChallengeCompletion).filter(
            SpeakingChallengeCompletion.client_session_id == session_id
        )
        if user_id is None:
            query = query.filter(SpeakingChallengeCompletion.user_id.is_(None))
        else:
            query = query.filter(SpeakingChallengeCompletion.user_id == user_id)
        return query.count()

    def _conversation_count(self, *, session_id: str, user_id: int | None) -> int:
        if user_id is not None:
            return self.db.query(Conversation).filter(Conversation.user_id == user_id).count()
        return self.db.query(Message.conversation_id).filter(
            Message.role == "user",
            Message.metadata_json["session_id"].as_string() == session_id,
        ).distinct().count()

    def _average_fluency_score(self, messages: list[Message]) -> int | None:
        scores = []
        for message in messages:
            metadata = message.metadata_json or {}
            score = metadata.get("fluency_score")
            if isinstance(score, int):
                scores.append(score)
        if not scores:
            return None
        return round(sum(scores) / len(scores))

    def _learning_goals(self, *, user: User | None, messages: list[Message]) -> list[str]:
        goals = []
        if user is not None and user.full_name:
            goals.append("Build a consistent English speaking profile")
        for message in messages[:12]:
            text = message.content.lower()
            for pattern in (
                r"i want to improve ([a-z ]+)",
                r"i want improve ([a-z ]+)",
                r"my goal is ([a-z ]+)",
                r"ina son koyon ([a-z ]+)",
            ):
                match = re.search(pattern, text)
                if match:
                    goal = match.group(1).strip(" .,!?:;")
                    if goal and goal not in goals:
                        goals.append(goal)
        return goals[:4] or ["Speak more confidently in English"]

    def _daily_recommendations(
        self,
        *,
        issues: list[LearningIssue],
        completed_challenges: int,
        average_fluency_score: int | None,
        learning_goals: list[str],
    ) -> list[RecommendationItemResponse]:
        recommendations = []
        top_issue = issues[0] if issues else None
        if top_issue is not None:
            recommendations.append(
                RecommendationItemResponse(
                    title=f"Review {top_issue.label}",
                    description=top_issue.recommendation,
                    category=top_issue.category,
                    priority=1,
                    reason=f"This pattern appeared {top_issue.count} times in your practice history.",
                    action_label="Start focused drill",
                )
            )
        recommendations.append(
            RecommendationItemResponse(
                title="Complete one speaking challenge",
                description="Choose today's beginner, intermediate, or advanced prompt and speak for the suggested time.",
                category="challenge",
                priority=2,
                reason=f"You have completed {completed_challenges} speaking challenges so far.",
                action_label="Open daily challenge",
            )
        )
        if average_fluency_score is None or average_fluency_score < 65:
            recommendations.append(
                RecommendationItemResponse(
                    title="Record a slow-and-clear answer",
                    description="Answer one prompt in three sentences, then repeat it once with smoother pacing.",
                    category="fluency",
                    priority=3,
                    reason="Conversation performance shows room to build fluency consistency.",
                    action_label="Practice speaking",
                )
            )
        else:
            recommendations.append(
                RecommendationItemResponse(
                    title="Stretch your answer length",
                    description="Give a two-minute answer with an example, a reason, and a conclusion.",
                    category="fluency",
                    priority=3,
                    reason=f"Your average fluency score is {average_fluency_score}, so you are ready for longer speaking.",
                    action_label="Try advanced response",
                )
            )
        recommendations.append(
            RecommendationItemResponse(
                title=f"Work toward: {learning_goals[0]}",
                description="Use today's chat practice to say one sentence directly connected to this goal.",
                category="goal",
                priority=4,
                reason="Your recommendations should stay connected to your personal learning goal.",
                action_label="Practice goal sentence",
            )
        )
        return recommendations[:4]

    def _targeted_topics(
        self,
        *,
        issues: list[LearningIssue],
        learning_goals: list[str],
    ) -> list[TargetedPracticeTopicResponse]:
        topics = []
        for issue in issues[:4]:
            topics.append(
                TargetedPracticeTopicResponse(
                    topic=issue.label,
                    prompt=self._prompt_for_issue(issue),
                    focus_area=issue.category,
                    difficulty=self._difficulty_for_count(issue.count),
                    estimated_minutes=5 if issue.count < 3 else 8,
                )
            )
        if len(topics) < 3:
            topics.append(
                TargetedPracticeTopicResponse(
                    topic="Personal Goal Practice",
                    prompt=f"Speak for one minute about this goal: {learning_goals[0]}. Say why it matters and what you will do next.",
                    focus_area="goal",
                    difficulty="beginner",
                    estimated_minutes=5,
                )
            )
        return topics[:5]

    def _improvement_suggestions(
        self,
        *,
        issues: list[LearningIssue],
        average_fluency_score: int | None,
        conversation_count: int,
    ) -> list[RecommendationItemResponse]:
        suggestions = []
        grammar_total = sum(issue.count for issue in issues if issue.category == "grammar")
        vocabulary_total = sum(issue.count for issue in issues if issue.category == "vocabulary")
        structure_total = sum(issue.count for issue in issues if issue.category == "sentence_structure")
        if grammar_total:
            suggestions.append(self._suggestion("Reduce repeated grammar mistakes", "Rewrite three recent corrected sentences and say each one aloud.", "grammar", grammar_total, 1))
        if vocabulary_total:
            suggestions.append(self._suggestion("Grow vocabulary range", "Replace basic words with more precise alternatives in one short answer.", "vocabulary", vocabulary_total, 2))
        if structure_total:
            suggestions.append(self._suggestion("Improve sentence structure", "Use because, but, and so to connect three ideas naturally.", "sentence_structure", structure_total, 3))
        if conversation_count < 3:
            suggestions.append(
                RecommendationItemResponse(
                    title="Build more conversation history",
                    description="Complete at least three short conversations so Chazy can personalize recommendations more accurately.",
                    category="conversation",
                    priority=4,
                    reason=f"Only {conversation_count} conversation thread is available." if conversation_count == 1 else f"Only {conversation_count} conversation threads are available.",
                    action_label="Start conversation",
                )
            )
        if average_fluency_score is not None and average_fluency_score >= 75:
            suggestions.append(
                RecommendationItemResponse(
                    title="Move into longer answers",
                    description="Practice two-minute responses with a clear beginning, middle, and ending.",
                    category="fluency",
                    priority=5,
                    reason=f"Your average fluency score is {average_fluency_score}.",
                    action_label="Try long answer",
                )
            )
        return suggestions[:5]

    def _suggestion(self, title: str, description: str, category: str, count: int, priority: int) -> RecommendationItemResponse:
        return RecommendationItemResponse(
            title=title,
            description=description,
            category=category,
            priority=priority,
            reason=f"{count} related patterns were found in your history.",
            action_label="Practice now",
        )

    def _prompt_for_issue(self, issue: LearningIssue) -> str:
        if issue.category == "grammar":
            return f"Make five short spoken sentences that avoid this mistake: {issue.label}."
        if issue.category == "vocabulary":
            return f"Describe your day using five stronger words instead of repeating basic words. Focus on {issue.label}."
        if issue.category == "sentence_structure":
            return f"Answer one question using because, but, and so. Focus on {issue.label}."
        return f"Practice a short answer focused on {issue.label}."

    def _difficulty_for_count(self, count: int) -> str:
        if count >= 5:
            return "advanced"
        if count >= 3:
            return "intermediate"
        return "beginner"
