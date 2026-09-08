from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import (
    Action,
    AgentSuggestion,
    Context,
    Execution,
    Feedback,
    GestureObservation,
    GesturePattern,
    User,
)
from ..schemas import (
    DashboardResponse,
    FeedbackCreate,
    FeedbackResponse,
    InferenceResult,
    ObserveRequest,
    ObserveResponse,
    PatternRead,
    SuggestionRead,
    SuggestionResponse,
    SuggestionResponseRequest,
    TeachRequest,
    TeachResponse,
)
from ..services.feedback_service import record_feedback
from ..services.gesture_encoder import encode_gesture, gesture_key
from ..services.intent_reasoner import infer_intent
from ..services.pattern_learning import record_user_action, respond_to_suggestion

router = APIRouter(tags=["agent"])


def _get_or_404(db: Session, model: type, key: str, label: str):
    instance = db.get(model, key)
    if instance is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return instance


@router.post("/observe", response_model=ObserveResponse)
def observe(payload: ObserveRequest, db: Session = Depends(get_db)) -> dict:
    _get_or_404(db, User, payload.user_id, "User")
    context = Context(
        id=str(uuid4()),
        user_id=payload.user_id,
        active_app=payload.context.active_app,
        activity=payload.context.activity,
        space=payload.context.space,
        device=payload.context.device,
    )
    observation = GestureObservation(
        id=str(uuid4()),
        user_id=payload.user_id,
        context_id=context.id,
        gesture_key=gesture_key(payload.gesture.motion_type, payload.gesture.direction),
        gesture_embedding=payload.gesture.embedding
        or encode_gesture(
            payload.gesture.motion_type,
            payload.gesture.direction,
            payload.gesture.duration_ms,
        ),
        motion_type=payload.gesture.motion_type,
        direction=payload.gesture.direction,
        duration_ms=payload.gesture.duration_ms,
        frame_stored=False,
    )
    db.add_all([context, observation])
    db.commit()

    inference = (
        infer_intent(db, observation, context)
        if payload.attempt_inference
        else InferenceResult(matched=False, reason="추론을 요청하지 않았습니다.")
    )
    return {"context": context, "observation": observation, "inference": inference}


@router.post("/teach", response_model=TeachResponse)
def teach(payload: TeachRequest, db: Session = Depends(get_db)) -> dict:
    _get_or_404(db, User, payload.user_id, "User")
    try:
        action, pattern, suggestion = record_user_action(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "action": action,
        "pattern": pattern,
        "suggestion": suggestion,
        "progress_current": min(pattern.observation_count, settings.suggestion_threshold),
        "progress_required": settings.suggestion_threshold,
    }


@router.get("/suggestions", response_model=list[SuggestionRead])
def list_suggestions(
    user_id: str,
    status: str | None = None,
    db: Session = Depends(get_db),
) -> list[AgentSuggestion]:
    _get_or_404(db, User, user_id, "User")
    stmt = select(AgentSuggestion).where(AgentSuggestion.user_id == user_id)
    if status:
        stmt = stmt.where(AgentSuggestion.status == status.upper())
    return list(db.scalars(stmt.order_by(desc(AgentSuggestion.created_at))).all())


@router.post("/suggestions/{suggestion_id}/respond", response_model=SuggestionResponse)
def respond_suggestion(
    suggestion_id: str,
    payload: SuggestionResponseRequest,
    db: Session = Depends(get_db),
) -> dict:
    suggestion = _get_or_404(db, AgentSuggestion, suggestion_id, "Suggestion")
    try:
        updated, pattern = respond_to_suggestion(
            db, suggestion, payload.decision, payload.modified_intent
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"suggestion": updated, "pattern": pattern}


@router.get("/memories", response_model=list[PatternRead])
def list_memories(
    user_id: str,
    gesture_key: str | None = None,
    context_scope: str | None = None,
    db: Session = Depends(get_db),
) -> list[GesturePattern]:
    _get_or_404(db, User, user_id, "User")
    stmt = select(GesturePattern).where(
        GesturePattern.user_id == user_id,
        GesturePattern.status == "ACTIVE",
        GesturePattern.confidence >= settings.auto_execution_threshold,
    )
    if gesture_key:
        stmt = stmt.where(GesturePattern.gesture_key == gesture_key)
    if context_scope:
        stmt = stmt.where(GesturePattern.context_scope == context_scope)
    return list(db.scalars(stmt.order_by(desc(GesturePattern.updated_at))).all())


@router.post("/executions/{execution_id}/feedback", response_model=FeedbackResponse)
def submit_feedback(
    execution_id: str,
    payload: FeedbackCreate,
    db: Session = Depends(get_db),
) -> dict:
    execution = _get_or_404(db, Execution, execution_id, "Execution")
    try:
        feedback, pattern = record_feedback(
            db, execution, payload.user_id, payload.feedback_type, payload.corrected_intent
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"feedback": feedback, "pattern": pattern}


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(user_id: str, db: Session = Depends(get_db)) -> dict:
    _get_or_404(db, User, user_id, "User")

    def recent(model, order_column, *conditions, limit: int | None = None) -> list:
        stmt = (
            select(model)
            .where(model.user_id == user_id, *conditions)
            .order_by(desc(order_column))
            .limit(limit)
        )
        return list(db.scalars(stmt).all())

    def total(model) -> int:
        return db.scalar(select(func.count(model.id)).where(model.user_id == user_id)) or 0

    memories = recent(GesturePattern, GesturePattern.updated_at, GesturePattern.status == "ACTIVE")
    candidates = recent(
        GesturePattern, GesturePattern.updated_at, GesturePattern.status == "CANDIDATE"
    )
    suggestions = recent(
        AgentSuggestion, AgentSuggestion.created_at, AgentSuggestion.status == "PENDING"
    )
    observations = recent(GestureObservation, GestureObservation.detected_at, limit=8)
    actions = recent(Action, Action.executed_at, limit=8)
    executions = recent(Execution, Execution.executed_at, limit=8)

    events = [
        {
            "time": item.detected_at,
            "type": "observation",
            "title": f"{item.motion_type} / {item.direction}",
            "detail": "원본 프레임은 저장하지 않고 특징 벡터만 기록",
        }
        for item in observations
    ] + [
        {
            "time": item.executed_at,
            "type": "action",
            "title": item.action_type,
            "detail": f"사용자 후속 행동 / {item.target}",
        }
        for item in actions
    ] + [
        {
            "time": item.executed_at,
            "type": "execution",
            "title": item.intent,
            "detail": item.error_message
            or f"Agent {item.status} / confidence {item.confidence:.0%}",
            "status": item.status,
        }
        for item in executions
    ]
    events.sort(key=lambda event: event["time"], reverse=True)

    return {
        "context": next(iter(recent(Context, Context.captured_at, limit=1)), None),
        "counts": {
            "observations": total(GestureObservation),
            "learned_memories": len(memories),
            "pending_suggestions": len(suggestions),
            "feedback": total(Feedback),
        },
        "memories": memories,
        "candidates": candidates,
        "suggestions": suggestions,
        "events": events[:12],
        "threshold": settings.suggestion_threshold,
    }
