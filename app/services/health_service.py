from app.config.settings import get_settings
from app.schemas.health import HealthResponse
from app.services.email_service import EmailService


class HealthService:
    @staticmethod
    def build_health_response() -> HealthResponse:
        settings = get_settings()
        return HealthResponse(
            status="ok",
            service=settings.app_name,
            environment=settings.environment,
            version=settings.app_version,
            email=EmailService().health_check(),
        )
