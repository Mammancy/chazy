from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    OpenAIError,
    RateLimitError,
)

from app.ai.english_learning_pipeline import GrammarAnalysis
from app.config.settings import get_settings

logger = logging.getLogger(__name__)
LearningResponse = dict[str, str]
FallbackResponseFactory = Callable[[], LearningResponse]


@dataclass(frozen=True)
class OpenAIServiceResult:
    text: str
    source: str
    fallback_used: bool
    attempts: int
    model: str
    learning_response: LearningResponse
    response_id: str | None = None
    response_status: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    usage: dict[str, Any] | None = None


class OpenAIService:
    """Production OpenAI service for CHAZY English speaking coach responses."""

    REQUIRED_KEYS = ("correction", "explanation", "reply", "suggested_topic", "vocabulary", "confidence_tip")

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = (settings.openai_api_key or "").strip() or None
        self._model = (settings.openai_model or "").strip() or "gpt-4.1-mini"
        self._timeout_seconds = max(float(settings.openai_timeout_seconds), 1.0)
        self._max_retries = max(int(settings.openai_max_retries), 0)
        self._retry_base_delay_seconds = max(float(settings.openai_retry_base_delay_seconds), 0.1)
        self._client = AsyncOpenAI(timeout=self._timeout_seconds, max_retries=0) if self._api_key else None
        self._log(
            logging.INFO,
            "openai_service_initialized",
            configured=bool(self._client),
            model=self._model,
            timeout_seconds=self._timeout_seconds,
            max_retries=self._max_retries,
            retry_base_delay_seconds=self._retry_base_delay_seconds,
            api="responses",
            mode="english_learning_pipeline",
        )

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key and self._client)

    async def generate_learning_response(
        self,
        *,
        system_prompt: str,
        grammar_analysis: GrammarAnalysis,
        coaching_context: dict[str, Any],
        request_id: str | None = None,
        fallback_response_factory: FallbackResponseFactory | None = None,
    ) -> OpenAIServiceResult:
        response_length_preference = str(coaching_context.get("response_length_preference") or "SHORT").upper()
        if not self.is_configured:
            return self._fallback_result(
                fallback_response_factory=fallback_response_factory,
                grammar_analysis=grammar_analysis,
                request_id=request_id,
                attempts=0,
                error_type="configuration_error",
                error_message="OPENAI_API_KEY is missing or empty.",
                response_length_preference=response_length_preference,
            )

        input_text = self._build_user_prompt(
            grammar_analysis=grammar_analysis,
            coaching_context=coaching_context,
        )
        request_payload = {
            "model": self._model,
            "instructions": system_prompt,
            "input": input_text,
            "temperature": 0.4,
            "max_output_tokens": self._max_output_tokens(response_length_preference),
        }
        max_attempts = self._max_retries + 1
        last_error: Exception | None = None

        self._log(
            logging.INFO,
            "openai_request_begin",
            request_id=request_id,
            model=self._model,
            max_attempts=max_attempts,
            coaching_focus=coaching_context.get("mistake_summary"),
            fluency_score=coaching_context.get("fluency_score"),
            grammar_mistakes_detected=grammar_analysis.has_grammar_mistakes,
            detected_mistakes=grammar_analysis.detected_mistakes,
            coaching_keys=sorted(coaching_context.keys()),
            original_message_chars=len(grammar_analysis.original_message),
            corrected_sentence_chars=len(grammar_analysis.corrected_sentence),
            input_chars=len(input_text),
            expected_schema=list(self.REQUIRED_KEYS),
        )

        for attempt in range(1, max_attempts + 1):
            started_at = time.perf_counter()
            try:
                self._log(
                    logging.INFO,
                    "openai_request_attempt",
                    request_id=request_id,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    model=self._model,
                    payload=self._safe_payload_for_logs(request_payload),
                )
                response = await self._client.responses.create(**request_payload)
                duration_ms = self._elapsed_ms(started_at)
                raw_text = self._extract_response_text(response).strip()
                learning_response = self._parse_learning_response(
                    raw_text,
                    grammar_analysis=grammar_analysis,
                    response_length_preference=response_length_preference,
                )
                usage = self._usage_to_dict(getattr(response, "usage", None))

                self._log(
                    logging.INFO,
                    "openai_response_success",
                    request_id=request_id,
                    attempt=attempt,
                    response_id=getattr(response, "id", None),
                    response_status=getattr(response, "status", None),
                    response_model=getattr(response, "model", None),
                    duration_ms=duration_ms,
                    usage=usage,
                    output_chars=len(raw_text),
                    parsed_keys=list(learning_response.keys()),
                )
                self._log(
                    logging.INFO,
                    "openai_learning_response",
                    request_id=request_id,
                    attempt=attempt,
                    learning_response=learning_response,
                )

                return OpenAIServiceResult(
                    text=learning_response["reply"],
                    source="openai_responses",
                    fallback_used=False,
                    attempts=attempt,
                    model=getattr(response, "model", None) or self._model,
                    learning_response=learning_response,
                    response_id=getattr(response, "id", None),
                    response_status=getattr(response, "status", None),
                    usage=usage,
                )
            except Exception as exc:
                last_error = exc
                duration_ms = self._elapsed_ms(started_at)
                retryable = self._is_retryable_error(exc)
                self._log(
                    logging.WARNING if retryable and attempt < max_attempts else logging.ERROR,
                    "openai_request_error",
                    request_id=request_id,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    retryable=retryable,
                    duration_ms=duration_ms,
                    error_type=exc.__class__.__name__,
                    error_message=str(exc),
                    status_code=getattr(exc, "status_code", None),
                )
                if not retryable or attempt >= max_attempts:
                    break
                await asyncio.sleep(self._retry_delay_seconds(attempt))

        return self._fallback_result(
            fallback_response_factory=fallback_response_factory,
            grammar_analysis=grammar_analysis,
            request_id=request_id,
            attempts=max_attempts,
            error_type=last_error.__class__.__name__ if last_error else "unknown_error",
            error_message=str(last_error) if last_error else "OpenAI request failed.",
            response_length_preference=response_length_preference,
        )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()

    def _fallback_result(
        self,
        *,
        fallback_response_factory: FallbackResponseFactory | None,
        grammar_analysis: GrammarAnalysis,
        request_id: str | None,
        attempts: int,
        error_type: str,
        error_message: str,
        response_length_preference: str,
    ) -> OpenAIServiceResult:
        learning_response = (
            fallback_response_factory()
            if fallback_response_factory is not None
            else {
                "correction": grammar_analysis.corrected_sentence,
                "explanation": "I corrected the sentence locally because the online English coach is unavailable.",
                "reply": "I am still here with you. Let us keep practicing step by step.",
                "suggested_topic": "Can you write one more sentence about this?",
            }
        )
        learning_response = self._normalize_learning_response(
            learning_response,
            grammar_analysis=grammar_analysis,
            response_length_preference=response_length_preference,
        )
        self._log(
            logging.INFO,
            "openai_fallback_response",
            request_id=request_id,
            attempts=attempts,
            error_type=error_type,
            error_message=error_message,
            learning_response=learning_response,
        )
        return OpenAIServiceResult(
            text=learning_response["reply"],
            source="temporary_response_engine",
            fallback_used=True,
            attempts=attempts,
            model=self._model,
            learning_response=learning_response,
            error_type=error_type,
            error_message=error_message,
        )

    def _retry_delay_seconds(self, attempt: int) -> float:
        exponential_delay = self._retry_base_delay_seconds * (2 ** (attempt - 1))
        jitter = random.uniform(0, self._retry_base_delay_seconds)
        return min(exponential_delay + jitter, 8.0)

    @staticmethod
    def _is_retryable_error(exc: Exception) -> bool:
        if isinstance(exc, (APITimeoutError, APIConnectionError, RateLimitError, OpenAIServiceEmptyResponseError)):
            return True
        if isinstance(exc, APIStatusError):
            return exc.status_code in {408, 409, 429} or exc.status_code >= 500
        if isinstance(exc, APIError):
            return True
        if isinstance(exc, OpenAIError):
            return False
        return isinstance(exc, OpenAIServiceInvalidJSONError)

    @staticmethod
    def _build_user_prompt(
        *,
        grammar_analysis: GrammarAnalysis,
        coaching_context: dict[str, Any],
    ) -> str:
        return "\n".join(
            [
                f"Grammar mistakes detected: {grammar_analysis.has_grammar_mistakes}",
                "Detected mistake categories:",
                json.dumps(grammar_analysis.detected_mistakes, ensure_ascii=False),
                "Original user message:",
                grammar_analysis.original_message,
                "Backend corrected sentence:",
                grammar_analysis.corrected_sentence,
                "Coaching context:",
                json.dumps(coaching_context, ensure_ascii=False, default=str),
                f"Response length preference: {coaching_context.get('response_length_preference', 'SHORT')}",
                f"Response length instruction: {coaching_context.get('response_length_instruction', 'SHORT: keep the full response under 60 words.')}",
                "Return strict JSON with correction, explanation, reply, suggested_topic, vocabulary, and confidence_tip.",
                "For SHORT mode, keep all JSON values together under 60 words.",
                "Keep explanation to one sentence, reply concise, and suggested_topic to one follow-up question.",
                "Avoid bullets, lectures, essays, long paragraphs, and repeated explanations.",
            ]
        )

    def _parse_learning_response(
        self,
        raw_text: str,
        *,
        grammar_analysis: GrammarAnalysis,
        response_length_preference: str,
    ) -> LearningResponse:
        if not raw_text:
            raise OpenAIServiceEmptyResponseError("OpenAI returned an empty response.")
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", raw_text)
            if not match:
                raise OpenAIServiceInvalidJSONError(f"OpenAI returned non-JSON text: {raw_text[:200]}")
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError as exc:
                raise OpenAIServiceInvalidJSONError(f"OpenAI returned invalid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise OpenAIServiceInvalidJSONError("OpenAI JSON response was not an object.")
        return self._normalize_learning_response(
            parsed,
            grammar_analysis=grammar_analysis,
            response_length_preference=response_length_preference,
        )

    def _normalize_learning_response(
        self,
        value: dict[str, Any],
        *,
        grammar_analysis: GrammarAnalysis,
        response_length_preference: str,
    ) -> LearningResponse:
        reply = value.get("reply", value.get("final_reply", ""))
        suggested_topic = value.get("suggested_topic", value.get("suggested_follow_up_question", ""))
        normalized = {
            "correction": self._short_text(value.get("correction") or grammar_analysis.corrected_sentence, 180),
            "explanation": self._first_sentence(value.get("explanation") or self._default_explanation(grammar_analysis), 160),
            "reply": self._first_sentence(reply or "Good, that sounds clear.", 140),
            "suggested_topic": self._as_question(suggested_topic or "Can you say one more sentence about that?"),
            "vocabulary": self._first_sentence(value.get("vocabulary") or "Try one stronger word in your next answer.", 140),
            "confidence_tip": self._first_sentence(value.get("confidence_tip") or "Speak slowly first, then repeat with more confidence.", 140),
        }
        if response_length_preference.upper() == "SHORT":
            return self._enforce_total_word_limit(normalized, 60)
        return normalized

    @staticmethod
    def _default_explanation(grammar_analysis: GrammarAnalysis) -> str:
        if not grammar_analysis.has_grammar_mistakes:
            return "Your sentence is clear; I polished it to sound more natural."
        return "I corrected the main grammar or word choice issue."

    @staticmethod
    def _short_text(value: Any, max_chars: int) -> str:
        text = " ".join(str(value or "").replace("\n", " ").split())
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 1].rstrip() + "."

    @classmethod
    def _first_sentence(cls, value: Any, max_chars: int) -> str:
        text = cls._short_text(value, max_chars)
        match = re.search(r"^(.+?[.!?])(\s|$)", text)
        return match.group(1).strip() if match else text

    @classmethod
    def _as_question(cls, value: Any) -> str:
        text = cls._first_sentence(value, 140).rstrip(".!")
        if not text:
            return "Can you say one more sentence about that?"
        return text if text.endswith("?") else f"{text}?"

    @staticmethod
    def _max_output_tokens(preference: str) -> int:
        if preference == "DETAILED":
            return 650
        if preference == "MEDIUM":
            return 380
        return 220

    @staticmethod
    def _enforce_total_word_limit(value: LearningResponse, max_words: int) -> LearningResponse:
        words_used = 0
        limited: LearningResponse = {}
        for key in ("correction", "explanation", "reply", "suggested_topic", "vocabulary", "confidence_tip"):
            words = str(value.get(key, "")).split()
            remaining = max_words - words_used
            if remaining <= 0:
                limited[key] = ""
                continue
            if len(words) > remaining:
                limited[key] = " ".join(words[:remaining]).rstrip(",;:") + "."
            else:
                limited[key] = value.get(key, "")
            words_used += len(str(limited[key]).split())
        return limited

    @staticmethod
    def _extract_response_text(response: Any) -> str:
        output_text = getattr(response, "output_text", None)
        if output_text:
            return str(output_text)
        parts: list[str] = []
        for output_item in getattr(response, "output", []) or []:
            for content_item in getattr(output_item, "content", []) or []:
                text = getattr(content_item, "text", None)
                if text:
                    parts.append(str(text))
        return "".join(parts)

    @staticmethod
    def _usage_to_dict(usage: Any) -> dict[str, Any] | None:
        if usage is None:
            return None
        if hasattr(usage, "model_dump"):
            return usage.model_dump(mode="json")
        return {
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
        }

    @staticmethod
    def _safe_payload_for_logs(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "model": payload.get("model"),
            "temperature": payload.get("temperature"),
            "max_output_tokens": payload.get("max_output_tokens"),
            "instructions_chars": len(str(payload.get("instructions", ""))),
            "input_chars": len(str(payload.get("input", ""))),
        }

    @staticmethod
    def _elapsed_ms(started_at: float) -> int:
        return int((time.perf_counter() - started_at) * 1000)

    @staticmethod
    def _log(level: int, event: str, **fields: Any) -> None:
        logger.log(level, json.dumps({"event": event, **fields}, ensure_ascii=False, default=str))


class OpenAIServiceEmptyResponseError(RuntimeError):
    pass


class OpenAIServiceInvalidJSONError(RuntimeError):
    pass





