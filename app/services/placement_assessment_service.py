from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.placement_assessment import PlacementAssessmentAnswer, PlacementAssessmentSession
from app.schemas.placement_assessment import (
    PlacementAnswerFeedbackResponse,
    PlacementAnswerSubmitRequest,
    PlacementAssessmentResultResponse,
    PlacementAssessmentStartRequest,
    PlacementAssessmentStartResponse,
    PlacementAssessmentStateResponse,
    PlacementLearningPlanResponse,
    PlacementQuestionResponse,
)


@dataclass(frozen=True)
class PlacementQuestion:
    question_id: str
    skill: str
    difficulty: str
    prompt: str
    question_type: str
    answer_keywords: list[str]
    max_score: int = 5
    options: tuple[str, ...] = ()


QUESTIONS = [
    PlacementQuestion("grammar_1", "grammar", "beginner", "Choose the correct sentence: A) She go to school. B) She goes to school.", "multiple_choice", ["b", "she goes to school"], options=("A) She go to school.", "B) She goes to school.")),
    PlacementQuestion("grammar_2", "grammar", "intermediate", "Rewrite this sentence correctly: I am agree with you because it make sense.", "rewrite", ["i agree with you because it makes sense", "i agree", "makes sense"]),
    PlacementQuestion("vocabulary_1", "vocabulary", "beginner", "Give a stronger word for 'good' and use it in a sentence.", "short_answer", ["excellent", "great", "wonderful", "impressive", "useful"]),
    PlacementQuestion("vocabulary_2", "vocabulary", "intermediate", "Explain the difference between 'borrow' and 'lend'.", "short_answer", ["borrow", "take", "lend", "give"]),
    PlacementQuestion("reading_1", "reading_comprehension", "beginner", "Read: 'Amina missed the bus, so she walked to school.' Why did Amina walk?", "short_answer", ["missed the bus", "missed bus", "bus"]),
    PlacementQuestion("reading_2", "reading_comprehension", "intermediate", "Read: 'Although the meeting was long, the team agreed on a clear plan.' What contrast does 'although' show?", "short_answer", ["meeting was long", "agreed", "clear plan", "contrast"]),
    PlacementQuestion("conversation_1", "conversational_ability", "beginner", "Introduce yourself in two complete English sentences.", "speaking_prompt", ["my name", "i am", "i live", "i work", "i study"]),
    PlacementQuestion("conversation_2", "conversational_ability", "intermediate", "You are in a job interview. Explain one strength and give an example.", "speaking_prompt", ["strength", "example", "because", "i can", "i have"]),
]


class PlacementAssessmentService:
    def __init__(self, db: Session):
        self.db = db

    def start(self, payload: PlacementAssessmentStartRequest) -> PlacementAssessmentStartResponse:
        session = PlacementAssessmentSession(
            session_id=payload.session_id,
            user_id=payload.user_id,
            total_questions=len(QUESTIONS),
            skill_scores={},
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return PlacementAssessmentStartResponse(
            assessment_session_id=session.id,
            session_id=session.session_id,
            user_id=session.user_id,
            status=session.status,
            current_step=session.current_step,
            total_questions=session.total_questions,
            first_question=self._question_response(QUESTIONS[0]),
            created_at=session.created_at,
        )

    def submit_answer(
        self,
        assessment_session_id: int,
        payload: PlacementAnswerSubmitRequest,
        user_id: int | None = None,
    ) -> PlacementAnswerFeedbackResponse:
        session = self.db.get(PlacementAssessmentSession, assessment_session_id)
        if session is None:
            raise ValueError("Placement assessment session not found.")
        self._authorize_session(session, user_id)
        if session.status == "completed":
            raise ValueError("Placement assessment is already completed.")
        question = self._question(payload.question_id)
        score, feedback = self._score(question, payload.answer)
        self.db.add(
            PlacementAssessmentAnswer(
                assessment_session_id=session.id,
                question_id=question.question_id,
                skill=question.skill,
                user_answer=payload.answer,
                score=score,
                max_score=question.max_score,
                feedback=feedback,
            )
        )
        session.current_step += 1
        completed = session.current_step >= session.total_questions
        next_question = None
        if completed:
            self._complete(session)
        else:
            next_question = self._question_response(QUESTIONS[session.current_step])
        self.db.commit()
        return PlacementAnswerFeedbackResponse(
            question_id=question.question_id,
            skill=question.skill,
            score=score,
            max_score=question.max_score,
            feedback=feedback,
            next_question=next_question,
            completed=completed,
        )

    def state(self, assessment_session_id: int, user_id: int | None = None) -> PlacementAssessmentStateResponse:
        session = self.db.get(PlacementAssessmentSession, assessment_session_id)
        if session is None:
            raise ValueError("Placement assessment session not found.")
        self._authorize_session(session, user_id)
        result = self.result(assessment_session_id, user_id=user_id) if session.status == "completed" else None
        next_question = None
        if session.status != "completed" and session.current_step < len(QUESTIONS):
            next_question = self._question_response(QUESTIONS[session.current_step])
        return PlacementAssessmentStateResponse(
            assessment_session_id=session.id,
            session_id=session.session_id,
            status=session.status,
            current_step=session.current_step,
            total_questions=session.total_questions,
            next_question=next_question,
            result=result,
        )

    def result(self, assessment_session_id: int, user_id: int | None = None) -> PlacementAssessmentResultResponse:
        session = self.db.get(PlacementAssessmentSession, assessment_session_id)
        if session is None:
            raise ValueError("Placement assessment session not found.")
        self._authorize_session(session, user_id)
        if session.status != "completed":
            self._complete(session)
            self.db.commit()
            self.db.refresh(session)
        return PlacementAssessmentResultResponse(
            assessment_session_id=session.id,
            session_id=session.session_id,
            user_id=session.user_id,
            status=session.status,
            proficiency_level=session.proficiency_level or "beginner",
            skill_scores=session.skill_scores or {},
            learning_plan=PlacementLearningPlanResponse(**(session.learning_plan or self._learning_plan("beginner", {}))),
            completed_at=session.completed_at,
        )

    @staticmethod
    def _authorize_session(session: PlacementAssessmentSession, user_id: int | None) -> None:
        if user_id is not None and session.user_id != user_id:
            raise PermissionError("Not authorized for this placement assessment.")

    def _complete(self, session: PlacementAssessmentSession) -> None:
        answers = list(
            self.db.scalars(
                select(PlacementAssessmentAnswer).where(PlacementAssessmentAnswer.assessment_session_id == session.id)
            ).all()
        )
        skill_scores = self._skill_scores(answers)
        level = self._level(skill_scores)
        session.status = "completed"
        session.skill_scores = skill_scores
        session.proficiency_level = level
        session.learning_plan = self._learning_plan(level, skill_scores)
        session.completed_at = datetime.now(timezone.utc)

    def _skill_scores(self, answers: list[PlacementAssessmentAnswer]) -> dict[str, int]:
        totals: dict[str, tuple[int, int]] = {}
        for answer in answers:
            score, max_score = totals.get(answer.skill, (0, 0))
            totals[answer.skill] = (score + answer.score, max_score + answer.max_score)
        return {
            skill: round((score / max_score) * 100) if max_score else 0
            for skill, (score, max_score) in totals.items()
        }

    def _level(self, skill_scores: dict[str, int]) -> str:
        average = round(sum(skill_scores.values()) / len(skill_scores)) if skill_scores else 0
        if average >= 82 and min(skill_scores.values(), default=0) >= 70:
            return "advanced"
        if average >= 55:
            return "intermediate"
        return "beginner"

    def _learning_plan(self, level: str, skill_scores: dict[str, int]) -> dict:
        weak_skills = [skill for skill, score in skill_scores.items() if score < 60] or ["conversational_ability"]
        focus_labels = [skill.replace("_", " ").title() for skill in weak_skills[:3]]
        if level == "advanced":
            starter_plan = [
                "Complete one advanced role-play conversation every day.",
                "Practice two-minute answers with examples and follow-up questions.",
                "Review academic and business vocabulary using spaced repetition.",
            ]
        elif level == "intermediate":
            starter_plan = [
                "Practice scenario conversations three times per week.",
                "Review recurring grammar mistakes before each chat session.",
                "Save five useful vocabulary words into your notebook weekly.",
            ]
        else:
            starter_plan = [
                "Write and say five complete English sentences every day.",
                "Complete beginner speaking challenges and pronunciation practice.",
                "Review new vocabulary after one day, three days, and seven days.",
            ]
        return {
            "level": level,
            "focus_areas": focus_labels,
            "weekly_goals": [
                "Finish at least three guided conversations.",
                "Review due vocabulary words with spaced repetition.",
                "Complete one daily speaking challenge for five days.",
            ],
            "recommended_modes": ["chat", "scenario", "vocabulary", "pronunciation"],
            "starter_plan": starter_plan,
        }

    def _score(self, question: PlacementQuestion, answer: str) -> tuple[int, str]:
        normalized = self._normalize(answer)
        keyword_hits = sum(1 for keyword in question.answer_keywords if keyword in normalized)
        length_bonus = 1 if len(normalized.split()) >= 8 and question.skill == "conversational_ability" else 0
        score = min(question.max_score, keyword_hits + length_bonus)
        if question.question_type == "multiple_choice" and ("b" == normalized.strip() or "she goes" in normalized):
            score = question.max_score
        if score >= 4:
            return score, "Strong answer. You showed clear control of this skill."
        if score >= 2:
            return score, "Partly correct. Add more precise language or a clearer example."
        return score, "Needs practice. Review the model answer pattern and try again aloud."

    def _question(self, question_id: str) -> PlacementQuestion:
        for question in QUESTIONS:
            if question.question_id == question_id:
                return question
        raise ValueError("Placement question not found.")

    def _question_response(self, question: PlacementQuestion) -> PlacementQuestionResponse:
        return PlacementQuestionResponse(
            question_id=question.question_id,
            skill=question.skill,
            difficulty=question.difficulty,
            prompt=question.prompt,
            question_type=question.question_type,
            options=list(question.options),
        )

    def _normalize(self, text: str) -> str:
        return re.sub(r"\s+", " ", text.lower().strip().replace(".", "")).strip()
