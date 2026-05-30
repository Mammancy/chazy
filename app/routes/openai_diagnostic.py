from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config.settings import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["openai-diagnostic"])

TEST_MESSAGE = "Hello from CHAZY"


@router.get("/test-openai")
async def test_openai() -> JSONResponse:
    """Standalone OpenAI diagnostic endpoint using the current Responses API."""
    settings = get_settings()
    api_key = (settings.openai_api_key or "").strip()
    model = (settings.openai_model or "").strip() or "gpt-4.1-mini"

    if not api_key:
        logger.error("OpenAI diagnostic failed: OPENAI_API_KEY is missing or empty")
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "message": TEST_MESSAGE,
                "model": model,
                "api": "responses",
                "raw_response": None,
                "usage": None,
                "error": {
                    "type": "configuration_error",
                    "message": "OPENAI_API_KEY is missing or empty.",
                },
            },
        )

    from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI, OpenAIError

    client = AsyncOpenAI()
    request_payload: dict[str, Any] = {
        "model": model,
        "instructions": "You are CHAZY. Reply briefly and clearly.",
        "input": TEST_MESSAGE,
        "temperature": 0.2,
        "max_output_tokens": 80,
    }

    logger.info(
        "OpenAI diagnostic Responses request started model=%s message=%r payload=%s",
        model,
        TEST_MESSAGE,
        request_payload,
    )
    started_at = time.perf_counter()

    try:
        response = await client.responses.create(**request_payload)
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        raw_response = response.model_dump(mode="json")
        usage = raw_response.get("usage")
        response_model = raw_response.get("model") or model
        output_text = getattr(response, "output_text", "") or _extract_response_text(response)

        logger.info(
            "OpenAI diagnostic Responses response received response_id=%s model=%s status=%s duration_ms=%s usage=%s output_text=%s raw_response=%s",
            raw_response.get("id"),
            response_model,
            raw_response.get("status"),
            duration_ms,
            usage,
            output_text,
            raw_response,
        )

        return JSONResponse(
            status_code=200,
            content={
                "ok": True,
                "message": TEST_MESSAGE,
                "api": "responses",
                "model": response_model,
                "configured_model": model,
                "duration_ms": duration_ms,
                "output_text": output_text,
                "usage": usage,
                "raw_response": raw_response,
                "error": None,
            },
        )
    except APIStatusError as exc:
        return _openai_error_response(
            exc=exc,
            model=model,
            started_at=started_at,
            error_type="api_status_error",
            status_code=exc.status_code,
            extra={
                "response_status_code": exc.status_code,
                "response_body": getattr(exc, "response", None).text if getattr(exc, "response", None) else None,
            },
        )
    except APITimeoutError as exc:
        return _openai_error_response(
            exc=exc,
            model=model,
            started_at=started_at,
            error_type="api_timeout_error",
            status_code=504,
        )
    except APIConnectionError as exc:
        return _openai_error_response(
            exc=exc,
            model=model,
            started_at=started_at,
            error_type="api_connection_error",
            status_code=502,
        )
    except OpenAIError as exc:
        return _openai_error_response(
            exc=exc,
            model=model,
            started_at=started_at,
            error_type="openai_error",
            status_code=502,
        )
    except Exception as exc:
        return _openai_error_response(
            exc=exc,
            model=model,
            started_at=started_at,
            error_type="unexpected_error",
            status_code=500,
        )


def _openai_error_response(
    *,
    exc: Exception,
    model: str,
    started_at: float,
    error_type: str,
    status_code: int,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    duration_ms = int((time.perf_counter() - started_at) * 1000)
    error_payload: dict[str, Any] = {
        "type": error_type,
        "message": str(exc),
        "exception_class": exc.__class__.__name__,
    }
    if extra:
        error_payload.update(extra)

    logger.exception(
        "OpenAI diagnostic Responses failed model=%s duration_ms=%s error_type=%s error=%s extra=%s",
        model,
        duration_ms,
        error_type,
        exc,
        extra,
    )

    return JSONResponse(
        status_code=status_code,
        content={
            "ok": False,
            "message": TEST_MESSAGE,
            "api": "responses",
            "model": model,
            "configured_model": model,
            "duration_ms": duration_ms,
            "usage": None,
            "raw_response": None,
            "error": error_payload,
        },
    )


def _extract_response_text(response: Any) -> str:
    parts: list[str] = []
    for output_item in getattr(response, "output", []) or []:
        for content_item in getattr(output_item, "content", []) or []:
            text = getattr(content_item, "text", None)
            if text:
                parts.append(str(text))
    return "".join(parts)

