from __future__ import annotations

import logging

from app.services.email_service import EmailConfigurationError, EmailService

logger = logging.getLogger(__name__)


def validate_smtp_startup_configuration() -> bool:
    email_service = EmailService()
    health = email_service.health_check()
    if not health["configured"]:
        logger.warning(
            "SMTP startup validation incomplete: missing=%s issues=%s host=%s port=%s tls=%s ssl=%s",
            ", ".join(health["missing"]),
            " ".join(health["issues"]),
            health["host"] or "<unset>",
            health["port"],
            health["tls_enabled"],
            health["ssl_enabled"],
        )
        return False

    try:
        email_service._validate_config()
    except EmailConfigurationError as exc:
        logger.warning("SMTP startup validation failed: %s", exc)
        return False

    logger.info(
        "SMTP startup validation passed host=%s port=%s tls=%s ssl=%s from_email_configured=%s username_configured=%s",
        health["host"],
        health["port"],
        health["tls_enabled"],
        health["ssl_enabled"],
        health["from_email_configured"],
        health["username_configured"],
    )
    return True
