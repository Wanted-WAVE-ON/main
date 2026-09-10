from collections import Counter
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Action, AgentSuggestion, Context, GestureObservation, GesturePattern
from ..schemas import TeachRequest
from .action_catalog import CONTEXT_INTENTS, action_label

LEARNING_WINDOW = timedelta(days=30)
MAX_LEARNING_ACTIONS = 20


def _utc(value: datetime) -> datetime:
    # SQLite returns naive values even for DateTime(timezone=True).
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


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

    now = datetime.now(timezone.utc)
    action = Action(
        id=str(uuid4()),
        user_id=request.user_id,
        observation_id=observation.id,
        action_type=request.action_type,
        target=request.target,
        parameters=request.parameters,
        executed_by="USER",
        executed_at=now,
    )
    db.add(action)
    db.flush()

    # Bound the evidence so a long-established habit can still change. Agent
    # executions are never votes for the mapping that produced them.
    rows = db.execute(
        select(Action, GestureObservation)
        .join(GestureObservation, Action.observation_id == GestureObservation.id)
        .join(Context, GestureObservation.context_id == Context.id)
        .where(
            Action.user_id == request.user_id,
            Action.executed_by == "USER",
            Action.executed_at >= now - LEARNING_WINDOW,
            Action.executed_at <= now,
            GestureObservation.gesture_key == observation.gesture_key,
            Context.activity == context.activity,
        )
        .order_by(Action.executed_at.desc(), Action.id.desc())
        .limit(MAX_LEARNING_ACTIONS)
    ).all()

    ranked_actions = Counter(row.Action.action_type for row in rows).most_common(2)
    winning_intent, winning_count = ranked_actions[0]
    has_unique_winner = len(ranked_actions) == 1 or winning_count > ranked_actions[1][1]
    confidence = _confidence(winning_count, len(rows))
    winning_rows = [row for row in rows if row.Action.action_type == winning_intent]
    # Rows are newest first, so Counter's insertion order breaks target ties
    # using the most recent target rather than an arbitrary database row.
    winning_target = Counter(row.Action.target for row in winning_rows).most_common(1)[0][0]
    latest_winner = winning_rows[0].GestureObservation
    embedding_size = len(latest_winner.gesture_embedding)
    embeddings = [
        row.GestureObservation.gesture_embedding
        for row in winning_rows
        if len(row.GestureObservation.gesture_embedding) == embedding_size
    ]
    winning_embedding = [
        round(sum(values) / len(embeddings), 6)
        for values in zip(*embeddings, strict=True)
    ]

    last_rejected_at = db.scalar(
        select(func.max(AgentSuggestion.responded_at))
        .join(GesturePattern, AgentSuggestion.gesture_pattern_id == GesturePattern.id)
        .where(
            GesturePattern.user_id == request.user_id,
            GesturePattern.gesture_key == observation.gesture_key,
            GesturePattern.context_scope == context.activity,
            AgentSuggestion.suggested_intent == winning_intent,
            AgentSuggestion.status == "REJECTED",
        )
    )
    fresh_count = sum(
        last_rejected_at is None or _utc(row.Action.executed_at) > _utc(last_rejected_at)
        for row in winning_rows
    )
    rejection_cleared = last_rejected_at is None or fresh_count >= settings.suggestion_threshold

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
            gesture_embedding=winning_embedding,
            motion_type=latest_winner.motion_type,
            direction=latest_winner.direction,
            intent=winning_intent,
            context_scope=context.activity,
            target=winning_target,
            confidence=confidence,
            observation_count=winning_count,
            auto_execute=False,
            status="CANDIDATE" if rejection_cleared else "REJECTED",
        )
        db.add(pattern)
    else:
        pattern.gesture_embedding = winning_embedding
        pattern.target = winning_target
        pattern.confidence = confidence
        pattern.observation_count = winning_count
        if pattern.status == "REJECTED" and rejection_cleared:
            pattern.status = "CANDIDATE"

    db.flush()

    scope_patterns = db.scalars(
        select(GesturePattern).where(
            GesturePattern.user_id == request.user_id,
            GesturePattern.gesture_key == observation.gesture_key,
            GesturePattern.context_scope == context.activity,
        )
    ).all()
    for item in scope_patterns:
        if item.status == "ACTIVE" and (not has_unique_winner or item.id != pattern.id):
            item.status = "CANDIDATE"
            item.auto_execute = False

    eligible = (
        has_unique_winner
        and winning_count >= settings.suggestion_threshold
        and rejection_cleared
        and pattern.status != "ACTIVE"
    )
    suggestion: AgentSuggestion | None = None
    for pending in db.scalars(
        select(AgentSuggestion).where(
            AgentSuggestion.gesture_pattern_id.in_([item.id for item in scope_patterns]),
            AgentSuggestion.status == "PENDING",
        )
    ):
        if eligible and pending.gesture_pattern_id == pattern.id and suggestion is None:
            suggestion = pending
        else:
            db.delete(pending)

    if eligible:
        reason = (
            f"{context.activity} 상황에서 최근 30일 내 최대 20건의 조작 중 "
            f"유사한 동작 후 '{action_label(winning_intent)}' 행동이 "
            f"{winning_count}회 관찰되었습니다."
        )
        if suggestion is None:
            suggestion = AgentSuggestion(
                id=str(uuid4()),
                user_id=request.user_id,
                gesture_pattern_id=pattern.id,
                suggested_intent=winning_intent,
                reason=reason,
                confidence=confidence,
                status="PENDING",
            )
            db.add(suggestion)
        else:
            suggestion.suggested_intent = winning_intent
            suggestion.reason = reason
            suggestion.confidence = confidence

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
