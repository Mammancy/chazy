from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.english_learning_pipeline import GrammarAnalysis
from app.models.learning_analytics import LearningIssue
from app.schemas.learning_analytics import (
    LearningAnalyticsResponse,
    LearningIssueResponse,
    PracticeRecommendationResponse,
)


GRAMMAR_RECOMMENDATIONS = {
    "capitalization": "Practice rewriting five sentences that start with I, names, and places.",
    "punctuation": "Read short sentences aloud and add a full stop or question mark after each complete idea.",
    "subject_verb_agreement": "Practice present-tense pairs: I am, you are, he is, she is, they are.",
    "word_choice": "Replace casual forms like wanna, gonna, and alot with standard English forms.",
    "empty_message": "Practice answering with one complete sentence before expanding your idea.",
}

VOCABULARY_HINTS = {
    "basic_emotion_words": {"good", "bad", "nice", "happy", "sad"},
    "basic_action_words": {"do", "make", "go", "get", "thing"},
    "repeated_intensifiers": {"very", "really", "so"},
}


class LearningAnalyticsService:
    def __init__(self, db: Session):
        self.db = db

    def track_message(
        self,
        *,
        session_id: str,
        user_id: int | None,
        message: str,
        grammar_analysis: GrammarAnalysis,
    ) -> None:
        for mistake in grammar_analysis.detected_mistakes:
            self._upsert_issue(
                session_id=session_id,
                user_id=user_id,
                category="grammar",
                issue_key=mistake,
                label=mistake.replace("_", " ").title(),
                example=message,
                recommendation=GRAMMAR_RECOMMENDATIONS.get(
                    mistake,
                    "Review this grammar pattern and write three corrected examples.",
                ),
            )

        for issue_key, label, recommendation in self._detect_vocabulary_issues(message):
            self._upsert_issue(
                session_id=session_id,
                user_id=user_id,
                category="vocabulary",
                issue_key=issue_key,
                label=label,
                example=message,
                recommendation=recommendation,
            )

        for issue_key, label, recommendation in self._detect_sentence_structure_issues(message):
            self._upsert_issue(
                session_id=session_id,
                user_id=user_id,
                category="sentence_structure",
                issue_key=issue_key,
                label=label,
                example=message,
                recommendation=recommendation,
            )

        self.db.commit()

    def get_analytics(self, session_id: str, user_id: int | None = None) -> LearningAnalyticsResponse:
        issues = list(
            self.db.scalars(
                self._base_query(session_id, user_id)
                .order_by(LearningIssue.count.desc(), LearningIssue.last_seen_at.desc())
            ).all()
        )
        grammar = self._responses(issues, "grammar")
        vocabulary = self._responses(issues, "vocabulary")
        sentence_structure = self._responses(issues, "sentence_structure")
        return LearningAnalyticsResponse(
            session_id=session_id,
            user_id=user_id,
            total_issues=len(issues),
            recurring_grammar_mistakes=grammar,
            vocabulary_weaknesses=vocabulary,
            sentence_structure_issues=sentence_structure,
            recommendations=self._recommendations(grammar, vocabulary, sentence_structure),
        )

    def _upsert_issue(
        self,
        *,
        session_id: str,
        user_id: int | None,
        category: str,
        issue_key: str,
        label: str,
        example: str,
        recommendation: str,
    ) -> None:
        issue = self.db.scalar(
            select(LearningIssue).where(
                LearningIssue.session_id == session_id,
                LearningIssue.user_id == user_id,
                LearningIssue.category == category,
                LearningIssue.issue_key == issue_key,
            ).limit(1)
        )
        if issue is None:
            self.db.add(
                LearningIssue(
                    session_id=session_id,
                    user_id=user_id,
                    category=category,
                    issue_key=issue_key,
                    label=label,
                    example=example,
                    recommendation=recommendation,
                    count=1,
                    last_seen_at=datetime.now(timezone.utc),
                )
            )
            return
        issue.count += 1
        issue.example = example
        issue.recommendation = recommendation
        issue.last_seen_at = datetime.now(timezone.utc)

    def _base_query(self, session_id: str, user_id: int | None):
        query = select(LearningIssue).where(LearningIssue.session_id == session_id)
        if user_id is not None:
            query = query.where(LearningIssue.user_id == user_id)
        return query

    def _detect_vocabulary_issues(self, message: str) -> list[tuple[str, str, str]]:
        words = [word.lower() for word in re.findall(r"[A-Za-z']+", message)]
        word_set = set(words)
        issues = []
        if len(words) >= 5 and len(word_set) <= max(3, len(words) // 2):
            issues.append((
                "limited_word_variety",
                "Limited Word Variety",
                "Retell the same idea with three new adjectives, verbs, or connectors.",
            ))
        if word_set & VOCABULARY_HINTS["basic_emotion_words"]:
            issues.append((
                "basic_emotion_words",
                "Basic Emotion Words",
                "Replace simple emotion words with precise ones like excited, worried, relieved, or disappointed.",
            ))
        if word_set & VOCABULARY_HINTS["basic_action_words"]:
            issues.append((
                "basic_action_words",
                "Basic Action Words",
                "Upgrade common verbs with clearer choices such as prepare, complete, receive, build, or visit.",
            ))
        if sum(1 for word in words if word in VOCABULARY_HINTS["repeated_intensifiers"]) >= 2:
            issues.append((
                "repeated_intensifiers",
                "Repeated Intensifiers",
                "Use stronger adjectives instead of repeating very, really, or so.",
            ))
        return issues

    def _detect_sentence_structure_issues(self, message: str) -> list[tuple[str, str, str]]:
        sentences = [part.strip() for part in re.split(r"[.!?]+", message) if part.strip()]
        words = re.findall(r"[A-Za-z']+", message)
        issues = []
        if len(words) > 22 and len(sentences) <= 1:
            issues.append((
                "run_on_sentence",
                "Run-On Sentence",
                "Split long ideas into two or three shorter sentences with one main idea each.",
            ))
        if sentences and all(len(re.findall(r"[A-Za-z']+", sentence)) < 5 for sentence in sentences):
            issues.append((
                "short_fragments",
                "Short Sentence Fragments",
                "Expand short answers with because, when, where, or an example.",
            ))
        lower = message.lower()
        if len(sentences) >= 2 and not any(connector in lower for connector in ("because", "but", "so", "then", "while", "although")):
            issues.append((
                "few_connectors",
                "Few Connecting Words",
                "Practice linking ideas with because, but, so, then, while, and although.",
            ))
        return issues

    def _responses(self, issues: list[LearningIssue], category: str) -> list[LearningIssueResponse]:
        return [
            LearningIssueResponse.model_validate(issue)
            for issue in issues
            if issue.category == category
        ][:10]

    def _recommendations(
        self,
        grammar: list[LearningIssueResponse],
        vocabulary: list[LearningIssueResponse],
        sentence_structure: list[LearningIssueResponse],
    ) -> list[PracticeRecommendationResponse]:
        recommendations = []
        for priority, issue in enumerate((grammar + vocabulary + sentence_structure)[:6], start=1):
            recommendations.append(
                PracticeRecommendationResponse(
                    title=f"Practice {issue.label}",
                    description=issue.recommendation,
                    category=issue.category,
                    priority=priority,
                )
            )
        if not recommendations:
            recommendations.append(
                PracticeRecommendationResponse(
                    title="Keep Building Speaking Range",
                    description="Send a few more practice messages so Chazy can personalize your recommendations.",
                    category="general",
                    priority=1,
                )
            )
        return recommendations
