from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.auth import authenticated_session_id, get_current_user
from app.models.user import User
from app.schemas.placement_assessment import (
    PlacementAnswerFeedbackResponse,
    PlacementAnswerSubmitRequest,
    PlacementAssessmentResultResponse,
    PlacementAssessmentStartRequest,
    PlacementAssessmentStartResponse,
    PlacementAssessmentStateResponse,
)
from app.services.placement_assessment_service import PlacementAssessmentService

router = APIRouter(prefix="/placement-assessment", tags=["placement-assessment"])


def _placement_error(exc: ValueError) -> HTTPException:
    detail = str(exc)
    if "not found" in detail.lower():
        return HTTPException(status_code=404, detail=detail)
    if "not completed" in detail.lower() or "already completed" in detail.lower():
        return HTTPException(status_code=409, detail=detail)
    return HTTPException(status_code=422, detail=detail)


@router.post("/start", response_model=PlacementAssessmentStartResponse)
async def start_placement_assessment(
    payload: PlacementAssessmentStartRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PlacementAssessmentStartResponse:
    secure_payload = payload.model_copy(
        update={"session_id": authenticated_session_id(current_user), "user_id": current_user.id}
    )
    return PlacementAssessmentService(db).start(secure_payload)


@router.post("/{assessment_session_id}/answers", response_model=PlacementAnswerFeedbackResponse)
async def submit_placement_answer(
    assessment_session_id: int,
    payload: PlacementAnswerSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PlacementAnswerFeedbackResponse:
    try:
        return PlacementAssessmentService(db).submit_answer(assessment_session_id, payload, user_id=current_user.id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise _placement_error(exc) from exc


@router.get("/{assessment_session_id}", response_model=PlacementAssessmentStateResponse)
async def get_placement_assessment_state(
    assessment_session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PlacementAssessmentStateResponse:
    try:
        return PlacementAssessmentService(db).state(assessment_session_id, user_id=current_user.id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise _placement_error(exc) from exc


@router.get("/{assessment_session_id}/result", response_model=PlacementAssessmentResultResponse)
async def get_placement_assessment_result(
    assessment_session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PlacementAssessmentResultResponse:
    try:
        return PlacementAssessmentService(db).result(assessment_session_id, user_id=current_user.id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise _placement_error(exc) from exc
