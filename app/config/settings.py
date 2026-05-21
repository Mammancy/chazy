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


class Settings(BaseModel):
    app_name: str = Field(default=os.getenv("APP_NAME", "ABOKI Companion AI"))
    app_version: str = Field(default=os.getenv("APP_VERSION", "0.1.0"))
    environment: str = Field(default=os.getenv("ENVIRONMENT", "development"))
    debug: bool = Field(default=os.getenv("DEBUG", "false").lower() == "true")
    log_level: str = Field(default=os.getenv("LOG_LEVEL", "INFO"))
    api_v1_prefix: str = Field(default=os.getenv("API_V1_PREFIX", "/api/v1"))
    database_url: str = Field(default=os.getenv("DATABASE_URL", "sqlite:///./aboki.db"))
    openai_api_key: str | None = Field(default=os.getenv("OPENAI_API_KEY"))
    openai_model: str = Field(default=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
    openai_timeout_seconds: float = Field(default=_env_float("OPENAI_TIMEOUT_SECONDS", 30.0))
    openai_max_retries: int = Field(default=_env_int("OPENAI_MAX_RETRIES", 2))
    openai_retry_base_delay_seconds: float = Field(default=_env_float("OPENAI_RETRY_BASE_DELAY_SECONDS", 0.5))
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
