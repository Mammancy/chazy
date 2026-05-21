from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import OpenAIService, TemporaryConversationalResponseEngine
from app.ai.english_learning_pipeline import EnglishLearningPipeline, GrammarAnalysis
from app.ai.personality import CHAZY_SYSTEM_PROMPT
from app.emotions.analyzer import EmotionAnalyzer
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ConversationHistoryMessage,
    ConversationHistoryResponse,
)
from app.services.memory_management_service import MemoryManagementService

_TEMP_RESPONSE_ENGINE = TemporaryConversationalResponseEngine()
_EMOTION_ANALYZER = EmotionAnalyzer()
_ENGLISH_PIPELINE = EnglishLearningPipeline()
_OPENAI_SERVICE = OpenAIService()
logger = logging.getLogger(__name__)


class ChatService:
    """Application use-case service for English learning chat interactions."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.memory_service = MemoryManagementService(db)

    async def process_message(self, payload: ChatRequest, request_id: str | None = None) -> ChatResponse:
        user = self._resolve_user(payload)
        conversation = self._resolve_conversation(payload=payload, user=user)
        grammar_analysis = _ENGLISH_PIPELINE.analyze(payload.message)

        user_message_record = self.memory_service.store_conversation_history(
            conversation_id=conversation.id,
            user_id=user.id,
            role="user",
            content=payload.message,
            metadata={
                "session_id": payload.session_id,
                "request_id": request_id,
                "conversation_id": conversation.id,
                "source": "english_learning_chat_api",
                "saved_automatically": True,
                "grammar_mistakes_detected": grammar_analysis.has_grammar_mistakes,
                "detected_mistakes": grammar_analysis.detected_mistakes,
                "corrected_sentence": grammar_analysis.corrected_sentence,
            },
        )

        emotion_analysis = _EMOTION_ANALYZER.analyze(payload.message)
        emotion_tone = emotion_analysis.emotion
        self.memory_service.store_emotional_pattern(
            user_id=user.id,
            conversation_id=conversation.id,
            message_id=user_message_record.id,
            emotion=emotion_tone,
            intensity=emotion_analysis.intensity,
            trigger_text=payload.message,
            metadata={
                "session_id": payload.session_id,
                "request_id": request_id,
                "sentiment": emotion_analysis.sentiment,
                "matched_keywords": emotion_analysis.matched_keywords,
                "learning_mode": "english_conversation",
                "grammar_mistakes_detected": grammar_analysis.has_grammar_mistakes,
                "detected_mistakes": grammar_analysis.detected_mistakes,
            },
        )

        details = self._extract_user_details(payload.message)
        for key, value in details.items():
            self.memory_service.store_user_detail(
                user_id=user.id,
                detail_key=key,
                detail_value=value,
                conversation_id=conversation.id,
                metadata={"session_id": payload.session_id, "request_id": request_id},
            )

        memory_context = self.memory_service.build_memory_snapshot(
            user_id=user.id,
            conversation_id=conversation.id,
        )
        learning_response, response_source = await self._generate_assistant_reply(
            session_id=payload.session_id,
            user_message=payload.message,
            emotion_tone=emotion_tone,
            grammar_analysis=grammar_analysis,
            memory_context=memory_context,
            request_id=request_id,
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
                "source": "english_learning_chat_api",
                "response_source": response_source,
                "emotion_tone": emotion_tone,
                "learning_response": learning_response,
                "grammar_mistakes_detected": grammar_analysis.has_grammar_mistakes,
                "detected_mistakes": grammar_analysis.detected_mistakes,
                "saved_automatically": True,
                "paired_user_message_id": user_message_record.id,
            },
        )

        live_context = _TEMP_RESPONSE_ENGINE.get_memory_context(session_id=payload.session_id)
        summary = live_context.get("memory_summaries", [])[-1] if live_context.get("memory_summaries") else None
        if summary:
            self.memory_service.store_memory_summary(
                user_id=user.id,
                conversation_id=conversation.id,
                summary=summary,
                metadata={
                    "source": "english_learning_response_engine",
                    "session_id": payload.session_id,
                    "request_id": request_id,
                },
            )
            memory_context = self.memory_service.build_memory_snapshot(
                user_id=user.id,
                conversation_id=conversation.id,
            )

        return ChatResponse(
            session_id=payload.session_id,
            user_id=user.id,
            conversation_id=conversation.id,
            status=response_source,
            emotion_tone=emotion_tone,
            user_message=payload.message,
            grammar_mistakes_detected=grammar_analysis.has_grammar_mistakes,
            detected_mistakes=grammar_analysis.detected_mistakes,
            correction=learning_response["correction"],
            explanation=learning_response["explanation"],
            reply=learning_response["reply"],
            suggested_topic=learning_response["suggested_topic"],
            assistant_message=learning_response["reply"],
            user_message_id=user_message_record.id,
            assistant_message_id=assistant_message_record.id,
            memory_context=memory_context,
            request_id=request_id,
            created_at=datetime.now(timezone.utc),
        )

    async def _generate_assistant_reply(
        self,
        *,
        session_id: str,
        user_message: str,
        emotion_tone: str,
        grammar_analysis: GrammarAnalysis,
        memory_context: dict[str, Any],
        request_id: str | None = None,
    ) -> tuple[dict[str, str], str]:
        result = await _OPENAI_SERVICE.generate_learning_response(
            system_prompt=CHAZY_SYSTEM_PROMPT,
            grammar_analysis=grammar_analysis,
            memory_context=memory_context,
            emotional_state=emotion_tone,
            request_id=request_id,
            fallback_response_factory=lambda: _TEMP_RESPONSE_ENGINE.generate_learning_response(
                session_id=session_id,
                user_message=user_message,
                grammar_analysis=grammar_analysis,
            ),
        )
        return result.learning_response, result.source

    def get_conversation_history(
        self,
        *,
        session_id: str,
        conversation_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ConversationHistoryResponse:
        user = self._resolve_user_by_session(session_id)
        conversation = self._resolve_history_conversation(
            user=user,
            conversation_id=conversation_id,
        )

        messages = list(
            self.db.scalars(
                select(Message)
                .where(Message.conversation_id == conversation.id)
                .order_by(Message.created_at.asc(), Message.id.asc())
                .offset(offset)
                .limit(limit)
            ).all()
        )
        memory_context = self.memory_service.build_memory_snapshot(
            user_id=user.id,
            conversation_id=conversation.id,
        )

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
            memory_context=memory_context,
            limit=limit,
            offset=offset,
            count=len(messages),
        )

    def _resolve_user(self, payload: ChatRequest) -> User:
        if payload.user_id is not None:
            user = self.db.get(User, payload.user_id)
            if user is not None:
                return user

        user = self.db.scalar(select(User).where(User.external_id == payload.session_id).limit(1))
        if user is not None:
            return user

        user = User(
            external_id=payload.session_id,
            full_name=f"CHAZY English Learner {payload.session_id[:8]}",
            is_active=True,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def _resolve_user_by_session(self, session_id: str) -> User:
        user = self.db.scalar(select(User).where(User.external_id == session_id).limit(1))
        if user is not None:
            return user

        user = User(
            external_id=session_id,
            full_name=f"CHAZY English Learner {session_id[:8]}",
            is_active=True,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def _resolve_history_conversation(
        self,
        *,
        user: User,
        conversation_id: int | None = None,
    ) -> Conversation:
        if conversation_id is not None:
            conversation = self.db.get(Conversation, conversation_id)
            if conversation is not None and conversation.user_id == user.id:
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
            title="English Practice Conversation",
            summary="Auto-created for English learning conversation history retrieval.",
            status="active",
        )
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def _resolve_conversation(self, *, payload: ChatRequest, user: User) -> Conversation:
        if payload.conversation_id is not None:
            conversation = self.db.get(Conversation, payload.conversation_id)
            if conversation is not None and conversation.user_id == user.id:
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
            title=title or "English Practice Conversation",
            summary="Auto-created from first English learning chat message.",
            status="active",
        )
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    @staticmethod
    def _extract_user_details(message: str) -> dict[str, str]:
        lower = message.lower()
        extracted: dict[str, str] = {}
        patterns = {
            "name": "my name is ",
            "likes": "i like ",
            "work": "i work as ",
            "location": "i live in ",
        }
        for key, marker in patterns.items():
            if marker in lower:
                value = message[lower.index(marker) + len(marker) :].strip(" .,!?")
                if value:
                    extracted[key] = value
        return extracted




