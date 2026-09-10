from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator

Activity = Literal["presentation", "music"]
SuggestionDecision = Literal["ACCEPTED", "REJECTED", "MODIFIED"]
FeedbackType = Literal["CORRECT", "WRONG_ACTION", "ACCIDENTAL_GESTURE", "IGNORE"]


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserCreate(APIModel):
    name: str = Field(min_length=1, max_length=100)
    id: str | None = None


class UserRead(ORMModel):
    id: str
    name: str
    created_at: datetime


class ContextInput(APIModel):
    active_app: str | None = Field(default=None, min_length=1, max_length=100)
    activity: Activity | None = None
    space: str = Field(default="unspecified", max_length=100)
    device: str = Field(default="laptop", max_length=100)


class ContextRead(ORMModel):
    id: str
    user_id: str
    active_app: str
    activity: str
    space: str
    device: str
    captured_at: datetime


class GestureInput(APIModel):
    motion_type: str = Field(min_length=1, max_length=50)
    direction: str = Field(default="none", max_length=30)
    duration_ms: int = Field(default=430, ge=0, le=10_000)
    speed: FiniteFloat | None = Field(default=None, ge=0, le=10)
    amplitude: FiniteFloat | None = Field(default=None, ge=0, le=10)
    embedding: list[FiniteFloat] | None = Field(default=None, min_length=4, max_length=64)

    @model_validator(mode="after")
    def measured_features_are_paired(self):
        if (self.speed is None) != (self.amplitude is None):
            raise ValueError("speed and amplitude must be provided together")
        if self.speed is not None and self.embedding is not None:
            raise ValueError("Provide measured features or an embedding, not both")
        return self


class ObservationRead(ORMModel):
    id: str
    user_id: str
    context_id: str
    gesture_key: str
    gesture_embedding: list[float]
    motion_type: str
    direction: str
    duration_ms: int
    frame_stored: bool
    detected_at: datetime


class ActionRead(ORMModel):
    id: str
    user_id: str
    observation_id: str
    action_type: str
    target: str
    parameters: dict[str, Any]
    executed_by: str
    executed_at: datetime


class PatternRead(ORMModel):
    id: str
    user_id: str
    gesture_key: str
    gesture_embedding: list[float]
    motion_type: str
    direction: str
    intent: str
    context_scope: str
    target: str
    confidence: float
    observation_count: int
    positive_feedback_count: int
    negative_feedback_count: int
    auto_execute: bool
    status: str
    created_at: datetime
    updated_at: datetime


class SuggestionRead(ORMModel):
    id: str
    user_id: str
    gesture_pattern_id: str
    suggested_intent: str
    modified_intent: str | None
    reason: str
    confidence: float
    status: str
    created_at: datetime
    responded_at: datetime | None


class ExecutionRead(ORMModel):
    id: str
    user_id: str
    gesture_pattern_id: str
    observation_id: str
    intent: str
    target: str
    parameters: dict[str, Any]
    confidence: float
    execution_mode: str
    status: str
    error_message: str | None
    executed_at: datetime


class InferenceResult(BaseModel):
    matched: bool
    intent: str | None = None
    target: str | None = None
    confidence: float = 0.0
    reason: str
    execution: ExecutionRead | None = None


class ObserveRequest(APIModel):
    user_id: str
    context: ContextInput
    gesture: GestureInput
    attempt_inference: bool = True


class ObserveResponse(BaseModel):
    context: ContextRead
    observation: ObservationRead
    inference: InferenceResult


class TeachRequest(APIModel):
    user_id: str
    observation_id: str
    action_type: str = Field(min_length=1, max_length=64)
    target: str = Field(min_length=1, max_length=100)
    parameters: dict[str, Any] = Field(default_factory=dict)


class TeachResponse(BaseModel):
    action: ActionRead
    pattern: PatternRead
    suggestion: SuggestionRead | None
    progress_current: int
    progress_required: int


class SuggestionResponseRequest(APIModel):
    decision: SuggestionDecision
    modified_intent: str | None = Field(default=None, max_length=64)


class FeedbackCreate(APIModel):
    user_id: str
    feedback_type: FeedbackType
    corrected_intent: str | None = Field(default=None, max_length=64)


class FeedbackRead(ORMModel):
    id: str
    user_id: str
    gesture_pattern_id: str
    execution_id: str
    feedback_type: str
    corrected_intent: str | None
    created_at: datetime


class FeedbackResponse(BaseModel):
    feedback: FeedbackRead
    pattern: PatternRead


class SuggestionResponse(BaseModel):
    suggestion: SuggestionRead
    pattern: PatternRead


class DashboardEvent(BaseModel):
    time: datetime
    type: str
    title: str
    detail: str
    status: str | None = None


class DashboardResponse(BaseModel):
    context: ContextRead | None
    counts: dict[str, int]
    memories: list[PatternRead]
    candidates: list[PatternRead]
    suggestions: list[SuggestionRead]
    events: list[DashboardEvent]
    threshold: int


class DemoBootstrapResponse(BaseModel):
    user: UserRead
    intent_labels: dict[str, str]
    suggestion_threshold: int
    auto_execution_threshold: float
    os_actions_enabled: bool
    demo_mode: bool


class DemoResetResponse(DemoBootstrapResponse):
    deleted_counts: dict[str, int]
