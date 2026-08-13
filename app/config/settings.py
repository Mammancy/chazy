import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=ENV_FILE, override=False)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() == "true"


DEFAULT_JWT_SECRET_KEY = "change-this-development-jwt-secret"
WEAK_JWT_SECRET_VALUES = {
    DEFAULT_JWT_SECRET_KEY,
    "secret",
    "jwt-secret",
    "test-jwt-secret",
    "development-jwt-secret",
    "change-me",
    "changeme",
    "password",
}


class Settings(BaseModel):
    app_name: str = Field(default=os.getenv("APP_NAME", "Confidence"))
    app_version: str = Field(default=os.getenv("APP_VERSION", "0.1.0"))
    environment: str = Field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    debug: bool = Field(default=os.getenv("DEBUG", "false").lower() == "true")
    log_level: str = Field(default=os.getenv("LOG_LEVEL", "INFO"))
    api_v1_prefix: str = Field(default=os.getenv("API_V1_PREFIX", "/api/v1"))
    database_url: str = Field(default=os.getenv("DATABASE_URL", "sqlite:///./chazy.db"))
    openai_api_key: str | None = Field(default=os.getenv("OPENAI_API_KEY"))
    openai_model: str = Field(default=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
    openai_timeout_seconds: float = Field(default=_env_float("OPENAI_TIMEOUT_SECONDS", 30.0))
    openai_max_retries: int = Field(default=_env_int("OPENAI_MAX_RETRIES", 2))
    openai_retry_base_delay_seconds: float = Field(default=_env_float("OPENAI_RETRY_BASE_DELAY_SECONDS", 0.5))
    openai_startup_client_check: bool = Field(default_factory=lambda: _env_bool("OPENAI_STARTUP_CLIENT_CHECK", False))
    smtp_host: str | None = Field(default_factory=lambda: os.getenv("SMTP_HOST"))
    smtp_port: int = Field(default_factory=lambda: _env_int("SMTP_PORT", 587))
    smtp_username: str | None = Field(default_factory=lambda: os.getenv("SMTP_USERNAME"))
    smtp_password: str | None = Field(default_factory=lambda: os.getenv("SMTP_PASSWORD"))
    smtp_from_email: str | None = Field(default_factory=lambda: os.getenv("SMTP_FROM_EMAIL"))
    smtp_use_tls: bool = Field(default_factory=lambda: _env_bool("SMTP_USE_TLS", True))
    smtp_use_ssl: bool = Field(default_factory=lambda: _env_bool("SMTP_USE_SSL", False))
    smtp_timeout_seconds: float = Field(default_factory=lambda: _env_float("SMTP_TIMEOUT_SECONDS", 20.0))
    password_reset_base_url: str = Field(default=os.getenv("PASSWORD_RESET_BASE_URL", "https://example.com/reset-password"))
    jwt_secret_key: str = Field(default_factory=lambda: os.getenv("JWT_SECRET_KEY", DEFAULT_JWT_SECRET_KEY))
    jwt_access_token_minutes: int = Field(default=_env_int("JWT_ACCESS_TOKEN_MINUTES", 30))
    jwt_refresh_token_days: int = Field(default=_env_int("JWT_REFRESH_TOKEN_DAYS", 30))
    jwt_issuer: str = Field(default=os.getenv("JWT_ISSUER", "chazy-api"))
    admin_emails: list[str] = Field(
        default_factory=lambda: [
            email.strip().lower()
            for email in os.getenv("ADMIN_EMAILS", "").split(",")
            if email.strip()
        ]
    )
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            origin.strip()
            for origin in os.getenv("CORS_ORIGINS", "*").split(",")
            if origin.strip()
        ]
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


def validate_production_jwt_secret(settings: Settings | None = None) -> None:
    active_settings = settings or get_settings()
    environment = active_settings.environment.strip().lower()
    if environment not in {"production", "prod"}:
        return

    secret = active_settings.jwt_secret_key.strip()
    weak_reasons = []
    if not secret:
        weak_reasons.append("it is empty")
    if secret in WEAK_JWT_SECRET_VALUES:
        weak_reasons.append("it uses a known default or test value")
    if len(secret) < 32:
        weak_reasons.append("it is shorter than 32 characters")
    lowered = secret.lower()
    if any(marker in lowered for marker in ("change-this", "changeme", "development", "default")):
        weak_reasons.append("it contains a placeholder marker")

    if weak_reasons:
        raise RuntimeError(
            "Refusing to start in production because JWT_SECRET_KEY is weak: "
            + "; ".join(dict.fromkeys(weak_reasons))
            + ". Set JWT_SECRET_KEY to a unique high-entropy secret."
        )


def validate_production_database_url(settings: Settings | None = None) -> None:
    active_settings = settings or get_settings()
    environment = active_settings.environment.strip().lower()
    if environment not in {"production", "prod"}:
        return

    configured_url = os.getenv("DATABASE_URL", "").strip()
    if not configured_url:
        raise RuntimeError(
            "Refusing to start in production because DATABASE_URL is not configured. "
            "Set DATABASE_URL to the hosted PostgreSQL connection URL."
        )

    normalized_url = configured_url.lower()
    if not (normalized_url.startswith("postgresql://") or normalized_url.startswith("postgres://") or normalized_url.startswith("postgresql+")):
        raise RuntimeError(
            "Refusing to start in production because DATABASE_URL is not a PostgreSQL URL. "
            "Set DATABASE_URL to the hosted PostgreSQL connection URL."
        )
