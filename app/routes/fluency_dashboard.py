from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.auth import authenticated_session_id, get_current_user
from app.models.user import User
from app.schemas.fluency_dashboard import FluencyDashboardResponse
from app.services.fluency_dashboard_service import FluencyDashboardService

router = APIRouter(prefix="/fluency-dashboard", tags=["fluency-dashboard"])


@router.get("/", response_model=FluencyDashboardResponse)
async def get_fluency_dashboard(
    session_id: str = Query(..., min_length=1),
    user_id: int | None = Query(default=None, ge=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FluencyDashboardResponse:
    return FluencyDashboardService(db).get_dashboard(
        session_id=authenticated_session_id(current_user),
        user_id=current_user.id,
    )
