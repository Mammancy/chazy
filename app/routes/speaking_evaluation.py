from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.speaking_evaluation import (
    SpeakingEvaluationHistoryResponse,
    SpeakingEvaluationRequest,
    SpeakingEvaluationResponse,
)
from app.services.speaking_evaluation_service import SpeakingEvaluationService

router = APIRouter(prefix="/speaking-evaluation", tags=["speaking-evaluation"])


@router.post("", response_model=SpeakingEvaluationResponse)
async def create_speaking_evaluation(
    payload: SpeakingEvaluationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SpeakingEvaluationResponse:
    return SpeakingEvaluationService(db).create(user=current_user, payload=payload)


@router.get("/history", response_model=SpeakingEvaluationHistoryResponse)
async def get_speaking_evaluation_history(
    limit: int = Query(default=10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SpeakingEvaluationHistoryResponse:
    return SpeakingEvaluationService(db).history(user_id=current_user.id, limit=limit)
