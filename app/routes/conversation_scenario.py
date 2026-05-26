from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.auth import authenticated_session_id, get_current_user
from app.models.user import User
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConversationScenarioListResponse:
    return ConversationScenarioService(db).list_scenarios()


@router.post("/sessions", response_model=ScenarioSessionResponse)
async def start_conversation_scenario(
    payload: ScenarioSessionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ScenarioSessionResponse:
    try:
        secure_payload = payload.model_copy(
            update={"session_id": authenticated_session_id(current_user), "user_id": current_user.id}
        )
        return ConversationScenarioService(db).start_session(secure_payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/sessions/{scenario_session_id}/turns", response_model=ScenarioTurnResponse)
async def continue_conversation_scenario(
    scenario_session_id: int,
    payload: ScenarioTurnRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ScenarioTurnResponse:
    try:
        return ConversationScenarioService(db).respond(scenario_session_id, payload, user_id=current_user.id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
