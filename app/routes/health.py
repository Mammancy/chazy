from fastapi import APIRouter

from app.schemas.health import HealthResponse
from app.services.health_service import HealthService

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthService.build_health_response()

