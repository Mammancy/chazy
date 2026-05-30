from __future__ import annotations

import logging

from app.config.settings import ENV_FILE, get_settings

logger = logging.getLogger(__name__)


async def validate_openai_startup_configuration() -> bool:
    """Validate local OpenAI configuration during FastAPI startup.

    This does not send a network request. The /test-openai endpoint remains the
    direct API-call diagnostic for credentials, quota, model access, and network.
    """
    settings = get_settings()
    api_key = (settings.openai_api_key or "").strip()
    model = (settings.openai_model or "").strip() or "gpt-4.1-mini"

    logger.info(
        "OpenAI startup validation started env_file=%s model=%s",
        ENV_FILE,
        model,
    )

    if not api_key:
        logger.error(
            "OpenAI startup validation failed: OPENAI_API_KEY is missing or empty. env_file=%s",
            ENV_FILE,
        )
        return False

    if not settings.openai_startup_client_check:
        logger.info(
            "OpenAI startup validation passed: OPENAI_API_KEY is present. Client initialization deferred until first OpenAI request. model=%s",
            model,
        )
        return True

    client: AsyncOpenAI | None = None
    try:
        from openai import AsyncOpenAI, OpenAIError

        client = AsyncOpenAI()
        logger.info(
            "OpenAI startup validation passed: OPENAI_API_KEY is present and AsyncOpenAI client initialized. model=%s",
            model,
        )
        return True
    except OpenAIError as exc:
        logger.exception(
            "OpenAI startup validation failed: AsyncOpenAI client initialization raised OpenAIError. model=%s error=%s",
            model,
            exc,
        )
        return False
    except Exception as exc:
        logger.exception(
            "OpenAI startup validation failed: unexpected client initialization error. model=%s error=%s",
            model,
            exc,
        )
        return False
    finally:
        if client is not None:
            await client.close()
