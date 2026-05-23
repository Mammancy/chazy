from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
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


@router.post("/start", response_model=PlacementAssessmentStartResponse)
async def start_placement_assessment(
    payload: PlacementAssessmentStartRequest,
    db: Session = Depends(get_db),
) -> PlacementAssessmentStartResponse:
    return PlacementAssessmentService(db).start(payload)


@router.post("/{assessment_session_id}/answers", response_model=PlacementAnswerFeedbackResponse)
async def submit_placement_answer(
    assessment_session_id: int,
    payload: PlacementAnswerSubmitRequest,
    db: Session = Depends(get_db),
) -> PlacementAnswerFeedbackResponse:
    try:
        return PlacementAssessmentService(db).submit_answer(assessment_session_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{assessment_session_id}", response_model=PlacementAssessmentStateResponse)
async def get_placement_assessment_state(
    assessment_session_id: int,
    db: Session = Depends(get_db),
) -> PlacementAssessmentStateResponse:
    try:
        return PlacementAssessmentService(db).state(assessment_session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{assessment_session_id}/result", response_model=PlacementAssessmentResultResponse)
async def get_placement_assessment_result(
    assessment_session_id: int,
    db: Session = Depends(get_db),
) -> PlacementAssessmentResultResponse:
    try:
        return PlacementAssessmentService(db).result(assessment_session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
