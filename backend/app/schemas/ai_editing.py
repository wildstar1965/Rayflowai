from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, ConfigDict, model_validator
from app.schemas.editing_actions import ACTION_REGISTRY

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
    "remove_subtitles", "style_subtitles", "generate_subtitles", "remove_title",
    "move_clip", "transform_clip", "delete_clip", "shorten_video", "remove_silence",
]


class AIAction(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: ActionType
    params: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode='after')
    def arguments(self):
        self.params = ACTION_REGISTRY[self.type].model_validate(self.params).model_dump(exclude_unset=True)
        return self


class AIEditingPlan(BaseModel):
    model_config = ConfigDict(extra='forbid')
    explanation: str = Field(min_length=1, max_length=2000)
    actions: List[AIAction] = Field(default_factory=list, max_length=20)
    clarification: Optional[str] = Field(default=None, max_length=1000)

    @model_validator(mode='after')
    def valid_sequence(self):
        if self.clarification and self.actions:
            raise ValueError('Clarification must not include executable actions.')
        if any(a.type in ('undo', 'redo') for a in self.actions) and len(self.actions) != 1:
            raise ValueError('Undo or redo must be a separate request before further edits.')
        return self


class ConversationTurn(BaseModel):
    role: Literal['user', 'assistant']
    content: str = Field(max_length=4000)


class EditorContext(BaseModel):
    selected_clip_id: Optional[str] = None
    selected_caption_ids: List[str] = Field(default_factory=list, max_length=500)
    playhead_time: float = Field(default=0, ge=0, allow_inf_nan=False)
    can_undo: bool = False
    can_redo: bool = False


class AIPlanRequest(BaseModel):
    command: str = Field(min_length=1, max_length=2000)
    current_plan: EditingPlan
    context: EditorContext = Field(default_factory=EditorContext)
    conversation: List[ConversationTurn] = Field(default_factory=list, max_length=20)


class AIApplyRequest(BaseModel):
    current_plan: EditingPlan
    ai_plan: AIEditingPlan


class AIPlanResponse(AIEditingPlan):
    proposed_plan: EditingPlan
    applied_changes: List[str] = Field(default_factory=list)
