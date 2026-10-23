from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.editing_plan import EditingPlan


ActionType = Literal[
    "add_subtitles",
    "set_aspect_ratio",
    "add_title",
    "add_transition",
    "set_clip_volume",
    "split_clip",
    "trim_clip",
    "undo",
    "redo",
]


class AIAction(BaseModel):
    type: ActionType
    params: Dict[str, Any] = Field(default_factory=dict)


class AIEditingPlan(BaseModel):
    explanation: str = Field(min_length=1, max_length=2000)
    actions: List[AIAction] = Field(default_factory=list, max_length=20)
    clarification: Optional[str] = Field(default=None, max_length=1000)


class AIPlanRequest(BaseModel):
    command: str = Field(min_length=1, max_length=2000)
    current_plan: EditingPlan


class AIApplyRequest(BaseModel):
    current_plan: EditingPlan
    ai_plan: AIEditingPlan


class AIPlanResponse(AIEditingPlan):
    proposed_plan: EditingPlan
    applied_changes: List[str] = Field(default_factory=list)
