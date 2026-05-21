from app.config.settings import get_settings
from app.schemas.health import HealthResponse


class HealthService:
    @staticmethod
    def build_health_response() -> HealthResponse:
        settings = get_settings()
        return HealthResponse(
            status="ok",
            service=settings.app_name,
            environment=settings.environment,
            version=settings.app_version,
        )

