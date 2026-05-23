from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.fluency_dashboard import FluencyDashboardResponse
from app.services.fluency_dashboard_service import FluencyDashboardService

router = APIRouter(prefix="/fluency-dashboard", tags=["fluency-dashboard"])


@router.get("/", response_model=FluencyDashboardResponse)
async def get_fluency_dashboard(
    session_id: str = Query(..., min_length=1),
    user_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> FluencyDashboardResponse:
    return FluencyDashboardService(db).get_dashboard(session_id=session_id, user_id=user_id)
