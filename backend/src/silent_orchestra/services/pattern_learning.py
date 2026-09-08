from collections import Counter
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Action, AgentSuggestion, Context, GestureObservation, GesturePattern
from ..schemas import TeachRequest
from .action_catalog import CONTEXT_INTENTS, action_label
from .gesture_encoder import running_average


def _confidence(winner_count: int, total_count: int) -> float:
    consistency = winner_count / total_count
    score = 0.35 + (0.10 * min(winner_count, 5)) + (0.22 * consistency)
    return round(min(0.99, score), 3)


def check_intent_change(db: Session, pattern: GesturePattern, intent: str, field: str) -> None:
    """Reject an intent the context forbids or that another memory already owns."""
    if intent not in CONTEXT_INTENTS.get(pattern.context_scope, ()):
        raise ValueError(f"{field} is not allowed for this context")
    duplicate = db.scalar(
        select(GesturePattern).where(
            GesturePattern.user_id == pattern.user_id,
            GesturePattern.gesture_key == pattern.gesture_key,
            GesturePattern.context_scope == pattern.context_scope,
            GesturePattern.intent == intent,
            GesturePattern.id != pattern.id,
        )
    )
    if duplicate is not None:
        raise ValueError("A gesture memory with this intent already exists")


def record_user_action(
    db: Session,
    request: TeachRequest,
) -> tuple[Action, GesturePattern, AgentSuggestion | None]:
    observation = db.get(GestureObservation, request.observation_id)
    if observation is None or observation.user_id != request.user_id:
        raise ValueError("Observation not found for this user")
    if observation.action is not None:
        raise ValueError("This observation already has a linked action")
    context = db.get(Context, observation.context_id)
    if context is None:
        raise ValueError("Context not found")
    if request.action_type not in CONTEXT_INTENTS.get(context.activity, ()):
        raise ValueError("action_type is not allowed for this context")

    action = Action(
        id=str(uuid4()),
        user_id=request.user_id,
        observation_id=observation.id,
        action_type=request.action_type,
        target=request.target,
        parameters=request.parameters,
        executed_by="USER",
    )
    db.add(action)
    db.flush()

    # Every action this user took after the same gesture in the same activity.
    rows = db.execute(
        select(Action.action_type, Action.target)
        .join(GestureObservation, Action.observation_id == GestureObservation.id)
        .join(Context, GestureObservation.context_id == Context.id)
        .where(
            Action.user_id == request.user_id,
            GestureObservation.gesture_key == observation.gesture_key,
            Context.activity == context.activity,
        )
    ).all()

    ranked_actions = Counter(row.action_type for row in rows).most_common(2)
    winning_intent, winning_count = ranked_actions[0]
    has_unique_winner = len(ranked_actions) == 1 or winning_count > ranked_actions[1][1]
    confidence = _confidence(winning_count, len(rows))
    winning_target = next(row.target for row in rows if row.action_type == winning_intent)

    pattern = db.scalar(
        select(GesturePattern).where(
            GesturePattern.user_id == request.user_id,
            GesturePattern.gesture_key == observation.gesture_key,
            GesturePattern.context_scope == context.activity,
            GesturePattern.intent == winning_intent,
        )
    )

    if pattern is None:
        pattern = GesturePattern(
            id=str(uuid4()),
            user_id=request.user_id,
            gesture_key=observation.gesture_key,
            gesture_embedding=observation.gesture_embedding,
            motion_type=observation.motion_type,
            direction=observation.direction,
            intent=winning_intent,
            context_scope=context.activity,
            target=winning_target,
            confidence=confidence,
            observation_count=winning_count,
            auto_execute=False,
            status="CANDIDATE",
        )
        db.add(pattern)
    else:
        pattern.gesture_embedding = running_average(
            pattern.gesture_embedding,
            observation.gesture_embedding,
            pattern.observation_count,
        )
        pattern.target = winning_target
        pattern.confidence = confidence
        pattern.observation_count = winning_count
        if pattern.status == "REJECTED":
            pattern.status = "CANDIDATE"

    db.flush()

    suggestion: AgentSuggestion | None = None
    if not has_unique_winner:
        # The gesture is ambiguous again: stop auto-executing it and withdraw
        # any suggestion that was still waiting for an answer.
        scope_patterns = db.scalars(
            select(GesturePattern).where(
                GesturePattern.user_id == request.user_id,
                GesturePattern.gesture_key == observation.gesture_key,
                GesturePattern.context_scope == context.activity,
            )
        ).all()
        for item in scope_patterns:
            if item.status == "ACTIVE":
                item.status = "CANDIDATE"
                item.auto_execute = False
        for pending in db.scalars(
            select(AgentSuggestion).where(
                AgentSuggestion.gesture_pattern_id.in_([item.id for item in scope_patterns]),
                AgentSuggestion.status == "PENDING",
            )
        ):
            db.delete(pending)
    elif winning_count >= settings.suggestion_threshold:
        suggestion = db.scalar(
            select(AgentSuggestion).where(
                AgentSuggestion.gesture_pattern_id == pattern.id,
                AgentSuggestion.status == "PENDING",
            )
        )
        if suggestion is None and pattern.status != "ACTIVE":
            suggestion = AgentSuggestion(
                id=str(uuid4()),
                user_id=request.user_id,
                gesture_pattern_id=pattern.id,
                suggested_intent=winning_intent,
                reason=(
                    f"{context.activity} 상황에서 유사한 동작 후 "
                    f"'{action_label(winning_intent)}' 행동이 {winning_count}회 관찰되었습니다."
                ),
                confidence=confidence,
                status="PENDING",
            )
            db.add(suggestion)

    db.commit()
    return action, pattern, suggestion


def respond_to_suggestion(
    db: Session,
    suggestion: AgentSuggestion,
    decision: str,
    modified_intent: str | None,
) -> tuple[AgentSuggestion, GesturePattern]:
    if suggestion.status != "PENDING":
        raise ValueError("Only pending suggestions can be answered")
    if decision not in {"ACCEPTED", "MODIFIED", "REJECTED"}:
        raise ValueError(f"Unsupported decision: {decision}")

    pattern = db.get(GesturePattern, suggestion.gesture_pattern_id)
    if pattern is None:
        raise ValueError("Gesture pattern not found")

    if decision == "MODIFIED":
        if not modified_intent:
            raise ValueError("modified_intent is required for MODIFIED")
        check_intent_change(db, pattern, modified_intent, "modified_intent")

    suggestion.status = decision
    suggestion.responded_at = datetime.now(timezone.utc)

    if decision == "REJECTED":
        pattern.status = "REJECTED"
        pattern.auto_execute = False
        pattern.confidence = max(0.0, round(pattern.confidence - 0.20, 3))
    else:
        if decision == "MODIFIED":
            suggestion.modified_intent = modified_intent
            pattern.intent = modified_intent
        # Only one memory per gesture may auto-execute in a given context.
        db.execute(
            update(GesturePattern)
            .where(
                GesturePattern.user_id == pattern.user_id,
                GesturePattern.gesture_key == pattern.gesture_key,
                GesturePattern.context_scope == pattern.context_scope,
                GesturePattern.id != pattern.id,
                GesturePattern.status == "ACTIVE",
            )
            .values(status="CANDIDATE", auto_execute=False)
        )
        pattern.status = "ACTIVE"
        pattern.auto_execute = True
        pattern.confidence = max(pattern.confidence, settings.auto_execution_threshold)

    db.commit()
    return suggestion, pattern
