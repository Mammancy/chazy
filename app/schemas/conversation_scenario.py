from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ConversationScenarioResponse(BaseModel):
    scenario_key: str
    category: str
    title: str
    description: str
    role: str
    user_role: str
    difficulty_levels: list[str]
    starter_prompt: str
    goals: list[str]
    useful_phrases: list[str]


class ConversationScenarioListResponse(BaseModel):
    scenarios: list[ConversationScenarioResponse]


class ScenarioSessionCreate(BaseModel):
    session_id: str = Field(..., min_length=1)
    user_id: int | None = Field(default=None, ge=1)
    scenario_key: str = Field(..., min_length=1)
    difficulty: str | None = None
    conversation_id: int | None = Field(default=None, ge=1)


class ScenarioTurnRequest(BaseModel):
    message: str = Field(..., min_length=1)
    user_message_id: int | None = Field(default=None, ge=1)
    assistant_message_id: int | None = Field(default=None, ge=1)


class ScenarioSessionResponse(BaseModel):
    scenario_session_id: int
    session_id: str
    user_id: int | None
    conversation_id: int | None
    scenario: ConversationScenarioResponse
    difficulty: str
    status: str
    current_step: int
    target_steps: int
    next_prompt: str
    coaching_tip: str
    useful_phrases: list[str]
    context: dict[str, Any]
    created_at: datetime


class ScenarioTurnResponse(BaseModel):
    scenario_session_id: int
    status: str
    step_number: int
    assistant_reply: str
    feedback: str
    next_prompt: str
    coaching_tip: str
    difficulty: str
    completed: bool
