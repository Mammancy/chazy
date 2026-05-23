from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.conversation_scenario import (
    ConversationScenarioListResponse,
    ScenarioSessionCreate,
    ScenarioSessionResponse,
    ScenarioTurnRequest,
    ScenarioTurnResponse,
)
from app.services.conversation_scenario_service import ConversationScenarioService

router = APIRouter(prefix="/conversation-scenarios", tags=["conversation-scenarios"])


@router.get("/", response_model=ConversationScenarioListResponse)
async def list_conversation_scenarios(
    db: Session = Depends(get_db),
) -> ConversationScenarioListResponse:
    return ConversationScenarioService(db).list_scenarios()


@router.post("/sessions", response_model=ScenarioSessionResponse)
async def start_conversation_scenario(
    payload: ScenarioSessionCreate,
    db: Session = Depends(get_db),
) -> ScenarioSessionResponse:
    try:
        return ConversationScenarioService(db).start_session(payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/sessions/{scenario_session_id}/turns", response_model=ScenarioTurnResponse)
async def continue_conversation_scenario(
    scenario_session_id: int,
    payload: ScenarioTurnRequest,
    db: Session = Depends(get_db),
) -> ScenarioTurnResponse:
    try:
        return ConversationScenarioService(db).respond(scenario_session_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
