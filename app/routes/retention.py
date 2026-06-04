from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.retention import RetentionSummaryResponse
from app.services.retention_service import RetentionService

router = APIRouter(prefix="/retention", tags=["retention"])


@router.get("/summary", response_model=RetentionSummaryResponse)
async def get_retention_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RetentionSummaryResponse:
    return RetentionService(db).summary(user=current_user)

