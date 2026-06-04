from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.speaking_evaluation import SpeakingEvaluation
from app.models.user import User
from app.schemas.speaking_evaluation import (
    SpeakingCorrection,
    SpeakingEvaluationHistoryResponse,
    SpeakingEvaluationRequest,
    SpeakingEvaluationResponse,
)


@dataclass(frozen=True)
class EvaluationResult:
    overall_score: int
    grammar_score: int
    fluency_score: int
    vocabulary_score: int
    confidence_score: int
    corrections: list[SpeakingCorrection]
    strengths: list[str]
    improvements: list[str]
    coach_feedback: str


class HeuristicSpeakingEvaluator:
    filler_words = {"um", "uh", "like", "you know", "actually", "basically"}
    correction_patterns = [
        (re.compile(r"\bI goes\b", re.IGNORECASE), "I go"),
        (re.compile(r"\bhe go\b", re.IGNORECASE), "he goes"),
        (re.compile(r"\bshe go\b", re.IGNORECASE), "she goes"),
        (re.compile(r"\bthey is\b", re.IGNORECASE), "they are"),
        (re.compile(r"\bwe was\b", re.IGNORECASE), "we were"),
        (re.compile(r"\bI was go\b", re.IGNORECASE), "I went"),
        (re.compile(r"\bI am agree\b", re.IGNORECASE), "I agree"),
        (re.compile(r"\bmore better\b", re.IGNORECASE), "better"),
        (re.compile(r"\bdid not went\b", re.IGNORECASE), "did not go"),
    ]

    def evaluate(self, *, transcript: str, duration_seconds: int) -> EvaluationResult:
        words = self._words(transcript)
        unique_words = {word.lower() for word in words}
        sentence_count = max(len(re.findall(r"[.!?]+", transcript)), 1)
        filler_count = self._filler_count(transcript)
        corrections = self._corrections(transcript)

        grammar_score = self._clamp(92 - len(corrections) * 12)
        if not transcript.strip().endswith((".", "!", "?")):
            grammar_score -= 6
        grammar_score = self._clamp(grammar_score)

        words_per_sentence = len(words) / sentence_count if sentence_count else len(words)
        filler_penalty = min(filler_count * 7, 30)
        fluency_score = self._clamp(55 + min(len(words), 80) // 2 - filler_penalty)
        if words_per_sentence < 5:
            fluency_score -= 8
        fluency_score = self._clamp(fluency_score)

        diversity = len(unique_words) / max(len(words), 1)
        vocabulary_score = self._clamp(45 + round(diversity * 45) + min(len(unique_words) // 4, 10))

        duration_score = min(duration_seconds * 1.6, 55)
        length_score = min(len(words) * 1.2, 45)
        confidence_score = self._clamp(round(duration_score + length_score - filler_penalty / 2))

        overall_score = self._clamp(
            round(
                grammar_score * 0.3
                + fluency_score * 0.25
                + vocabulary_score * 0.2
                + confidence_score * 0.25
            )
        )
        strengths, improvements = self._feedback_points(
            grammar_score=grammar_score,
            fluency_score=fluency_score,
            vocabulary_score=vocabulary_score,
            confidence_score=confidence_score,
            filler_count=filler_count,
        )
        coach_feedback = self._coach_feedback(overall_score, strengths, improvements)

        return EvaluationResult(
            overall_score=overall_score,
            grammar_score=grammar_score,
            fluency_score=fluency_score,
            vocabulary_score=vocabulary_score,
            confidence_score=confidence_score,
            corrections=corrections,
            strengths=strengths,
            improvements=improvements,
            coach_feedback=coach_feedback,
        )

    def _corrections(self, transcript: str) -> list[SpeakingCorrection]:
        corrections: list[SpeakingCorrection] = []
        for pattern, replacement in self.correction_patterns:
            match = pattern.search(transcript)
            if match:
                corrections.append(SpeakingCorrection(original=match.group(0), corrected=replacement))
        return corrections

    def _filler_count(self, transcript: str) -> int:
        lowered = transcript.lower()
        return sum(len(re.findall(rf"\b{re.escape(filler)}\b", lowered)) for filler in self.filler_words)

    @staticmethod
    def _words(transcript: str) -> list[str]:
        return re.findall(r"[A-Za-z']+", transcript)

    @staticmethod
    def _clamp(value: float | int) -> int:
        return max(0, min(100, round(value)))

    @staticmethod
    def _feedback_points(
        *,
        grammar_score: int,
        fluency_score: int,
        vocabulary_score: int,
        confidence_score: int,
        filler_count: int,
    ) -> tuple[list[str], list[str]]:
        strengths: list[str] = []
        improvements: list[str] = []

        if confidence_score >= 75:
            strengths.append("Good confidence")
        else:
            improvements.append("Speak for a little longer to build confidence")

        if fluency_score >= 75:
            strengths.append("Clear sentence structure")
        else:
            improvements.append("Use complete sentences and reduce pauses")

        if vocabulary_score >= 75:
            strengths.append("Good vocabulary variety")
        else:
            improvements.append("Expand vocabulary with more specific words")

        if grammar_score < 75:
            improvements.append("Review verb tense and subject agreement")
        else:
            strengths.append("Grammar is mostly controlled")

        if filler_count > 2:
            improvements.append("Reduce filler words such as um, uh, and like")

        return strengths[:3], improvements[:4]

    @staticmethod
    def _coach_feedback(overall_score: int, strengths: list[str], improvements: list[str]) -> str:
        if overall_score >= 80:
            opening = "Great effort. Your speaking foundation is strong."
        elif overall_score >= 60:
            opening = "Good effort. You are building a clear speaking rhythm."
        else:
            opening = "Keep practicing. Focus on short, complete answers first."

        strength_text = strengths[0].lower() if strengths else "your willingness to speak"
        improvement_text = improvements[0].lower() if improvements else "keep adding detail"
        return f"{opening} Your strength is {strength_text}, and your next focus is to {improvement_text}."


class SpeakingEvaluationService:
    def __init__(self, db: Session, evaluator: HeuristicSpeakingEvaluator | None = None):
        self.db = db
        self.evaluator = evaluator or HeuristicSpeakingEvaluator()

    def create(self, *, user: User, payload: SpeakingEvaluationRequest) -> SpeakingEvaluationResponse:
        transcript = payload.transcript.strip()
        result = self.evaluator.evaluate(
            transcript=transcript,
            duration_seconds=payload.duration_seconds,
        )
        evaluation = SpeakingEvaluation(
            user_id=user.id,
            transcript=transcript,
            duration_seconds=payload.duration_seconds,
            overall_score=result.overall_score,
            grammar_score=result.grammar_score,
            fluency_score=result.fluency_score,
            vocabulary_score=result.vocabulary_score,
            confidence_score=result.confidence_score,
            coach_feedback=result.coach_feedback,
        )
        self.db.add(evaluation)
        self.db.commit()
        self.db.refresh(evaluation)
        return self._response(evaluation, result=result)

    def history(self, *, user_id: int, limit: int = 10) -> SpeakingEvaluationHistoryResponse:
        evaluations = self.db.scalars(
            select(SpeakingEvaluation)
            .where(SpeakingEvaluation.user_id == user_id)
            .order_by(SpeakingEvaluation.created_at.desc(), SpeakingEvaluation.id.desc())
            .limit(limit)
        ).all()
        all_scores = self.db.scalars(
            select(SpeakingEvaluation.overall_score).where(SpeakingEvaluation.user_id == user_id)
        ).all()
        return SpeakingEvaluationHistoryResponse(
            evaluations=[self._response(evaluation) for evaluation in evaluations],
            evaluations_completed=len(all_scores),
            average_speaking_score=round(sum(all_scores) / len(all_scores), 1) if all_scores else 0.0,
            best_speaking_score=max(all_scores) if all_scores else 0,
        )

    def _response(
        self,
        evaluation: SpeakingEvaluation,
        result: EvaluationResult | None = None,
    ) -> SpeakingEvaluationResponse:
        if result is None:
            result = self.evaluator.evaluate(
                transcript=evaluation.transcript,
                duration_seconds=evaluation.duration_seconds,
            )
        return SpeakingEvaluationResponse(
            id=evaluation.id,
            overall_score=evaluation.overall_score,
            grammar_score=evaluation.grammar_score,
            fluency_score=evaluation.fluency_score,
            vocabulary_score=evaluation.vocabulary_score,
            confidence_score=evaluation.confidence_score,
            corrections=result.corrections,
            strengths=result.strengths,
            improvements=result.improvements,
            coach_feedback=evaluation.coach_feedback,
            transcript=evaluation.transcript,
            duration_seconds=evaluation.duration_seconds,
            created_at=evaluation.created_at,
        )
