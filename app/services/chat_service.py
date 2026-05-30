from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.english_learning_pipeline import EnglishLearningPipeline, GrammarAnalysis
from app.ai.personality import CHAZY_SYSTEM_PROMPT
from app.ai.temporary_response_engine import TemporaryConversationalResponseEngine
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ConversationHistoryMessage,
    ConversationHistoryResponse,
    GuidedLearningSessionResponse,
)
from app.services.coaching_service import CoachingMetrics, CoachingService
from app.services.conversation_scenario_service import ConversationScenarioService
from app.services.hausa_learning_service import HausaLearningService
from app.services.learning_analytics_service import LearningAnalyticsService
from app.services.memory_management_service import MemoryManagementService

_TEMP_RESPONSE_ENGINE = TemporaryConversationalResponseEngine()
_ENGLISH_PIPELINE = EnglishLearningPipeline()
_OPENAI_SERVICE = None
_COACHING_SERVICE = CoachingService()
_HAUSA_SERVICE = HausaLearningService()
logger = logging.getLogger(__name__)


def _get_openai_service():
    global _OPENAI_SERVICE
    if _OPENAI_SERVICE is None:
        from app.ai.openai_service import OpenAIService

        _OPENAI_SERVICE = OpenAIService()
    return _OPENAI_SERVICE


class ChatService:
    """Application service for AI English speaking coaching."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.memory_service = MemoryManagementService(db)
        self.analytics_service = LearningAnalyticsService(db)

    async def process_message(self, payload: ChatRequest, request_id: str | None = None) -> ChatResponse:
        user = self._resolve_user(payload)
        response_length_preference = self._resolve_response_length_preference(user, payload.response_length_preference)
        conversation = self._resolve_conversation(payload=payload, user=user)
        hausa_result = _HAUSA_SERVICE.process(payload.message)
        coaching_text = hausa_result.english_text if hausa_result.is_hausa else payload.message
        grammar_analysis = _ENGLISH_PIPELINE.analyze(coaching_text)
        coaching_metrics = _COACHING_SERVICE.build_metrics(text=coaching_text, grammar_analysis=grammar_analysis)
        coaching_context = self._build_coaching_context(
            payload=payload,
            conversation=conversation,
            grammar_analysis=grammar_analysis,
            coaching_metrics=coaching_metrics,
            response_length_preference=response_length_preference,
            hausa_result=hausa_result,
        )
        self.analytics_service.track_message(
            session_id=payload.session_id,
            user_id=user.id,
            message=coaching_text,
            grammar_analysis=grammar_analysis,
        )

        user_message_record = self.memory_service.store_conversation_history(
            conversation_id=conversation.id,
            user_id=user.id,
            role="user",
            content=payload.message,
            metadata={
                "session_id": payload.session_id,
                "request_id": request_id,
                "conversation_id": conversation.id,
                "source": "english_speaking_coach",
                "practice_mode": payload.practice_mode,
                "response_length_preference": response_length_preference,
                "saved_automatically": True,
                "input_language": "hausa" if hausa_result.is_hausa else "english",
                "translated_english": hausa_result.english_text if hausa_result.is_hausa else None,
                "translation_explanation": hausa_result.explanation if hausa_result.is_hausa else None,
                "detected_hausa_terms": hausa_result.detected_terms,
                "grammar_mistakes_detected": grammar_analysis.has_grammar_mistakes,
                "detected_mistakes": grammar_analysis.detected_mistakes,
                "corrected_sentence": grammar_analysis.corrected_sentence,
                "fluency_score": coaching_metrics.fluency_score,
                "vocabulary_suggestions": coaching_metrics.vocabulary_suggestions,
                "daily_challenge": coaching_metrics.daily_challenge,
                "speaking_prompt": coaching_metrics.speaking_prompt,
                "mistake_summary": coaching_metrics.mistake_summary,
            },
        )

        learning_response, response_source = await self._generate_assistant_reply(
            session_id=payload.session_id,
            user_message=coaching_text,
            grammar_analysis=grammar_analysis,
            coaching_context=coaching_context,
            request_id=request_id,
        )
        if hausa_result.is_hausa:
            learning_response = self._with_hausa_guidance(learning_response, hausa_result)
        scenario_turn = None
        if payload.practice_mode == "scenario":
            scenario_turn = ConversationScenarioService(self.db).chat_mode_reply(
                session_id=payload.session_id,
                user_id=user.id,
                conversation_id=conversation.id,
                message=coaching_text,
                user_message_id=user_message_record.id,
            )
            learning_response = self._with_scenario_guidance(learning_response, scenario_turn)
            response_source = f"{response_source}+scenario"
        guided_session = self._build_guided_session(
            payload=payload,
            conversation=conversation,
            grammar_analysis=grammar_analysis,
            coaching_metrics=coaching_metrics,
            learning_response=learning_response,
            scenario_turn=scenario_turn,
        )

        assistant_message_record = self.memory_service.store_conversation_history(
            conversation_id=conversation.id,
            user_id=None,
            role="assistant",
            content=learning_response["reply"],
            metadata={
                "session_id": payload.session_id,
                "request_id": request_id,
                "conversation_id": conversation.id,
                "source": "english_speaking_coach",
                "response_source": response_source,
                "practice_mode": payload.practice_mode,
                "response_length_preference": response_length_preference,
                "input_language": "hausa" if hausa_result.is_hausa else "english",
                "translated_english": hausa_result.english_text if hausa_result.is_hausa else None,
                "translation_explanation": hausa_result.explanation if hausa_result.is_hausa else None,
                "scenario_turn": scenario_turn.model_dump() if scenario_turn is not None else None,
                "learning_response": learning_response,
                "guided_session": guided_session.model_dump(),
                "coaching_context": coaching_context,
                "saved_automatically": True,
                "paired_user_message_id": user_message_record.id,
            },
        )

        return ChatResponse(
            session_id=payload.session_id,
            user_id=user.id,
            conversation_id=conversation.id,
            status=response_source,
            practice_mode=payload.practice_mode,
            response_length_preference=response_length_preference,
            user_message=payload.message,
            grammar_mistakes_detected=grammar_analysis.has_grammar_mistakes,
            detected_mistakes=grammar_analysis.detected_mistakes,
            correction=learning_response["correction"],
            explanation=learning_response["explanation"],
            reply=learning_response["reply"],
            suggested_topic=learning_response["suggested_topic"],
            vocabulary=learning_response.get("vocabulary", ""),
            confidence_tip=learning_response.get("confidence_tip", ""),
            assistant_message=learning_response["reply"],
            user_message_id=user_message_record.id,
            assistant_message_id=assistant_message_record.id,
            fluency_score=coaching_metrics.fluency_score,
            vocabulary_suggestions=coaching_metrics.vocabulary_suggestions,
            daily_challenge=coaching_metrics.daily_challenge,
            speaking_prompt=coaching_metrics.speaking_prompt,
            mistake_summary=coaching_metrics.mistake_summary,
            guided_session=guided_session,
            coaching_context=coaching_context,
            request_id=request_id,
            created_at=datetime.now(timezone.utc),
        )

    async def _generate_assistant_reply(
        self,
        *,
        session_id: str,
        user_message: str,
        grammar_analysis: GrammarAnalysis,
        coaching_context: dict[str, Any],
        request_id: str | None = None,
    ) -> tuple[dict[str, str], str]:
        result = await _get_openai_service().generate_learning_response(
            system_prompt=CHAZY_SYSTEM_PROMPT,
            grammar_analysis=grammar_analysis,
            coaching_context=coaching_context,
            request_id=request_id,
            fallback_response_factory=lambda: _TEMP_RESPONSE_ENGINE.generate_learning_response(
                session_id=session_id,
                user_message=user_message,
                grammar_analysis=grammar_analysis,
                coaching_context=coaching_context,
            ),
        )
        return result.learning_response, result.source

    def get_conversation_history(
        self,
        *,
        session_id: str,
        conversation_id: int | None = None,
        user_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ConversationHistoryResponse:
        user = self._resolve_user_by_session(session_id, user_id=user_id)
        conversation = self._resolve_history_conversation(user=user, conversation_id=conversation_id)
        messages = list(
            self.db.scalars(
                select(Message)
                .where(Message.conversation_id == conversation.id)
                .order_by(Message.created_at.asc(), Message.id.asc())
                .offset(offset)
                .limit(limit)
            ).all()
        )
        coaching_context = self._history_coaching_context(messages)
        return ConversationHistoryResponse(
            session_id=session_id,
            user_id=user.id,
            conversation_id=conversation.id,
            title=conversation.title,
            status=conversation.status,
            messages=[
                ConversationHistoryMessage(
                    id=message.id,
                    role=message.role,
                    content=message.content,
                    user_id=message.user_id,
                    metadata=message.metadata_json,
                    created_at=message.created_at,
                )
                for message in messages
            ],
            coaching_context=coaching_context,
            limit=limit,
            offset=offset,
            count=len(messages),
        )

    def _build_coaching_context(
        self,
        *,
        payload: ChatRequest,
        conversation: Conversation,
        grammar_analysis: GrammarAnalysis,
        coaching_metrics: CoachingMetrics,
        response_length_preference: str,
        hausa_result=None,
    ) -> dict[str, Any]:
        context = {
            "mode": payload.practice_mode,
            "response_length_preference": response_length_preference,
            "response_length_instruction": self._response_length_instruction(response_length_preference),
            "original_message": grammar_analysis.original_message,
            "corrected_sentence": grammar_analysis.corrected_sentence,
            "mistakes": grammar_analysis.detected_mistakes,
            "mistake_summary": coaching_metrics.mistake_summary,
            "fluency_score": coaching_metrics.fluency_score,
            "vocabulary_suggestions": coaching_metrics.vocabulary_suggestions,
            "daily_challenge": coaching_metrics.daily_challenge,
            "speaking_prompt": coaching_metrics.speaking_prompt,
            "recent_conversation": self._recent_conversation_context(conversation.id),
            "follow_up_instruction": (
                "Ask exactly one short follow-up question that is specific to the learner's latest "
                "message, recent conversation, interests, goals, practice mode, or recurring mistakes. "
                "Use generic follow-ups only when no meaningful context exists."
            ),
        }
        if hausa_result is not None and hausa_result.is_hausa:
            context.update(
                {
                    "input_language": "hausa",
                    "hausa_original": hausa_result.original_text,
                    "translated_english": hausa_result.english_text,
                    "translation_explanation": hausa_result.explanation,
                    "detected_hausa_terms": hausa_result.detected_terms,
                    "learning_instruction": "Continue in English after briefly explaining the Hausa-English translation.",
                }
            )
        return context

    def _recent_conversation_context(self, conversation_id: int) -> list[dict[str, str]]:
        messages = list(
            self.db.scalars(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(8)
            ).all()
        )
        recent = []
        for message in reversed(messages):
            content = " ".join(str(message.content or "").split())
            if not content:
                continue
            recent.append(
                {
                    "role": message.role,
                    "content": content[:220],
                }
            )
        return recent

    def _resolve_response_length_preference(self, user: User, requested: str | None) -> str:
        if requested is not None:
            preference = requested.upper()
            user.response_length_preference = preference
            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)
            return preference
        return (user.response_length_preference or "SHORT").upper()

    @staticmethod
    def _response_length_instruction(preference: str) -> str:
        if preference == "DETAILED":
            return "DETAILED: answer with helpful detail only when useful, but stay clear and organized."
        if preference == "MEDIUM":
            return "MEDIUM: answer in about 3 to 5 concise sentences."
        return "SHORT: default mode; keep the full response under 60 words."

    def _with_hausa_guidance(self, learning_response: dict[str, str], hausa_result) -> dict[str, str]:
        enhanced = dict(learning_response)
        enhanced["correction"] = hausa_result.english_text
        enhanced["explanation"] = f"Natural English: {hausa_result.english_text}"
        enhanced["reply"] = learning_response.get("reply", "Good, let's continue in English.")
        enhanced["suggested_topic"] = "Can you answer that again in English?"
        enhanced["confidence_tip"] = "Say the English version slowly once, then say it again naturally."
        return enhanced

    def _with_scenario_guidance(self, learning_response: dict[str, str], scenario_turn) -> dict[str, str]:
        enhanced = dict(learning_response)
        enhanced["reply"] = self._first_sentence(scenario_turn.assistant_reply)
        enhanced["suggested_topic"] = self._as_question(scenario_turn.next_prompt)
        enhanced["confidence_tip"] = scenario_turn.coaching_tip
        enhanced["explanation"] = self._first_sentence(scenario_turn.feedback)
        return enhanced

    def _build_guided_session(
        self,
        *,
        payload: ChatRequest,
        conversation: Conversation,
        grammar_analysis: GrammarAnalysis,
        coaching_metrics: CoachingMetrics,
        learning_response: dict[str, str],
        scenario_turn=None,
    ) -> GuidedLearningSessionResponse:
        turn_count = self.db.scalar(
            select(func.count(Message.id)).where(
                Message.conversation_id == conversation.id,
                Message.role == "user",
            )
        ) or 0
        mission_target = 5
        progress_percent = min(100, int((turn_count / mission_target) * 100))
        follow_ups = self._unique_short_list(
            [
                learning_response.get("suggested_topic", ""),
                coaching_metrics.speaking_prompt,
            ],
            limit=2,
        )
        topics = self._topic_suggestions(payload.practice_mode, grammar_analysis, coaching_metrics)
        vocabulary_hint = (
            coaching_metrics.vocabulary_suggestions[0]
            if coaching_metrics.vocabulary_suggestions
            else learning_response.get("vocabulary", "")
        )
        achievements = self._guided_achievements(
            turn_count=turn_count,
            practice_mode=payload.practice_mode,
            grammar_analysis=grammar_analysis,
            fluency_score=coaching_metrics.fluency_score,
        )
        return GuidedLearningSessionResponse(
            follow_up_questions=follow_ups,
            topic_suggestions=topics,
            conversation_mission=self._conversation_mission(payload.practice_mode, grammar_analysis),
            vocabulary_challenge=self._vocabulary_challenge(vocabulary_hint),
            roleplay_scenario=self._roleplay_scenario(payload.practice_mode, scenario_turn),
            completion_progress={
                "conversation_turns": turn_count,
                "mission_target_turns": mission_target,
                "mission_progress_percent": progress_percent,
                "fluency_score": coaching_metrics.fluency_score,
            },
            achievements=achievements,
            streak_update=self._streak_update(turn_count),
            learning_milestone=self._learning_milestone(turn_count, coaching_metrics.fluency_score),
        )

    def _topic_suggestions(
        self,
        practice_mode: str,
        grammar_analysis: GrammarAnalysis,
        coaching_metrics: CoachingMetrics,
    ) -> list[str]:
        topics = []
        if grammar_analysis.detected_mistakes:
            topics.append(f"Practice {grammar_analysis.detected_mistakes[0].replace('_', ' ')}")
        if practice_mode == "voice":
            topics.append("Speak your answer aloud")
        elif practice_mode == "scenario":
            topics.append("Continue the roleplay")
        else:
            topics.append("Answer with two full sentences")
        if coaching_metrics.vocabulary_suggestions:
            topics.append("Use one stronger word")
        return self._unique_short_list(topics, limit=3)

    @staticmethod
    def _conversation_mission(practice_mode: str, grammar_analysis: GrammarAnalysis) -> str:
        if practice_mode == "voice":
            return "Say your next answer aloud, then type the clearest version."
        if practice_mode == "scenario":
            return "Stay in character and answer with one natural sentence."
        if grammar_analysis.has_grammar_mistakes:
            return "Rewrite the corrected sentence, then add one new detail."
        return "Answer the follow-up with two complete sentences."

    @staticmethod
    def _vocabulary_challenge(vocabulary_hint: str) -> str:
        clean = " ".join(str(vocabulary_hint or "").split())
        if not clean:
            return "Use one specific adjective in your next answer."
        return f"Use this in your next reply: {clean}"

    @staticmethod
    def _roleplay_scenario(practice_mode: str, scenario_turn) -> str:
        if scenario_turn is not None:
            return "Roleplay: continue this real-life conversation naturally."
        if practice_mode == "voice":
            return "Roleplay: explain your opinion to a friendly classmate."
        return "Roleplay: answer like you are speaking to a coworker."

    @staticmethod
    def _guided_achievements(
        *,
        turn_count: int,
        practice_mode: str,
        grammar_analysis: GrammarAnalysis,
        fluency_score: int,
    ) -> list[str]:
        achievements = []
        if turn_count == 1:
            achievements.append("First conversation turn")
        if turn_count in {3, 5, 10}:
            achievements.append(f"{turn_count} speaking turns completed")
        if practice_mode == "voice":
            achievements.append("Voice practice started")
        if grammar_analysis.has_grammar_mistakes:
            achievements.append("Grammar correction reviewed")
        if fluency_score >= 75:
            achievements.append("Strong fluency score")
        return achievements[:3]

    @staticmethod
    def _streak_update(turn_count: int) -> str:
        if turn_count <= 1:
            return "Daily streak started."
        return f"Daily streak active with {turn_count} practice turns today."

    @staticmethod
    def _learning_milestone(turn_count: int, fluency_score: int) -> str:
        if turn_count >= 10:
            return "Milestone: extended conversation practice completed."
        if turn_count >= 5:
            return "Milestone: five-turn speaking practice completed."
        if fluency_score >= 75:
            return "Milestone: clear and confident sentence."
        return "Milestone: keep building this conversation."

    @staticmethod
    def _unique_short_list(values: list[str], *, limit: int) -> list[str]:
        seen = set()
        cleaned = []
        for value in values:
            item = " ".join(str(value or "").split())
            if not item or item.lower() in seen:
                continue
            seen.add(item.lower())
            cleaned.append(item[:120])
            if len(cleaned) >= limit:
                break
        return cleaned

    @staticmethod
    def _first_sentence(text: str | None) -> str:
        clean = " ".join(str(text or "").split())
        for marker in (".", "!", "?"):
            index = clean.find(marker)
            if index >= 0:
                return clean[: index + 1]
        return clean[:140]

    @classmethod
    def _as_question(cls, text: str | None) -> str:
        clean = cls._first_sentence(text).rstrip(".!")
        if not clean:
            return "What would you say next?"
        return clean if clean.endswith("?") else f"{clean}?"

    def _history_coaching_context(self, messages: list[Message]) -> dict[str, Any]:
        latest_metadata = next((m.metadata_json for m in reversed(messages) if m.metadata_json), {}) or {}
        return {
            "last_fluency_score": latest_metadata.get("fluency_score"),
            "last_mistake_summary": latest_metadata.get("mistake_summary"),
            "last_daily_challenge": latest_metadata.get("daily_challenge"),
        }

    def _resolve_user(self, payload: ChatRequest) -> User:
        if payload.user_id is not None:
            user = self.db.get(User, payload.user_id)
            if user is not None:
                return user
        user = self.db.scalar(select(User).where(User.external_id == payload.session_id).limit(1))
        if user is not None:
            return user
        user = User(external_id=payload.session_id, full_name=f"Chazy English Learner {payload.session_id[:8]}", is_active=True)
        user.response_length_preference = payload.response_length_preference or "SHORT"
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def _resolve_user_by_session(self, session_id: str, user_id: int | None = None) -> User:
        if user_id is not None:
            user = self.db.get(User, user_id)
            if user is not None:
                return user
        user = self.db.scalar(select(User).where(User.external_id == session_id).limit(1))
        if user is not None:
            return user
        user = User(external_id=session_id, full_name=f"Chazy English Learner {session_id[:8]}", is_active=True)
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def _resolve_history_conversation(self, *, user: User, conversation_id: int | None = None) -> Conversation:
        if conversation_id is not None:
            conversation = self.db.get(Conversation, conversation_id)
            if conversation is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
            if conversation.user_id != user.id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this conversation.")
            return conversation
        conversation = self.db.scalar(
            select(Conversation)
            .where(Conversation.user_id == user.id, Conversation.status == "active")
            .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
            .limit(1)
        )
        if conversation is not None:
            return conversation
        conversation = Conversation(
            user_id=user.id,
            title="English Speaking Practice",
            summary="Auto-created for English speaking coach conversation history.",
            status="active",
        )
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def _resolve_conversation(self, *, payload: ChatRequest, user: User) -> Conversation:
        if payload.conversation_id is not None:
            conversation = self.db.get(Conversation, payload.conversation_id)
            if conversation is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
            if conversation.user_id != user.id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this conversation.")
            return conversation
        conversation = self.db.scalar(
            select(Conversation)
            .where(Conversation.user_id == user.id, Conversation.status == "active")
            .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
            .limit(1)
        )
        if conversation is not None:
            return conversation
        title_seed = payload.message.strip().replace("\n", " ")
        title = (title_seed[:57] + "...") if len(title_seed) > 60 else title_seed
        conversation = Conversation(
            user_id=user.id,
            title=title or "English Speaking Practice",
            summary="Auto-created from first English speaking coach message.",
            status="active",
        )
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation
