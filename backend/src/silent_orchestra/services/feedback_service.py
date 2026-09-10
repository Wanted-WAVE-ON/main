from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Execution, Feedback, GesturePattern
from .pattern_learning import check_intent_change

DELTAS = {
    "CORRECT": 0.03,
    "WRONG_ACTION": -0.15,
    "ACCIDENTAL_GESTURE": 0.0,
    "IGNORE": -0.05,
}


def record_feedback(
    db: Session,
    execution: Execution,
    user_id: str,
    feedback_type: str,
    corrected_intent: str | None,
) -> tuple[Feedback, GesturePattern]:
    if execution.user_id != user_id:
        raise ValueError("Execution not found for this user")
    pattern = db.get(GesturePattern, execution.gesture_pattern_id)
    if pattern is None:
        raise ValueError("Gesture pattern not found")
    if db.scalar(select(Feedback).where(Feedback.execution_id == execution.id)) is not None:
        raise ValueError("Feedback already recorded for this execution")

    correcting = bool(corrected_intent) and feedback_type == "WRONG_ACTION"
    if correcting:
        check_intent_change(db, pattern, corrected_intent, "corrected_intent")

    feedback = Feedback(
        id=str(uuid4()),
        user_id=user_id,
        gesture_pattern_id=pattern.id,
        execution_id=execution.id,
        feedback_type=feedback_type,
        corrected_intent=corrected_intent,
    )
    db.add(feedback)

    pattern.confidence = round(min(0.99, max(0.0, pattern.confidence + DELTAS[feedback_type])), 3)
    if feedback_type == "CORRECT":
        pattern.positive_feedback_count += 1
    elif feedback_type != "ACCIDENTAL_GESTURE":
        pattern.negative_feedback_count += 1
    if correcting:
        pattern.intent = corrected_intent
    if pattern.confidence < settings.auto_execution_threshold:
        pattern.auto_execute = False
        pattern.status = "CANDIDATE"

    db.commit()
    return feedback, pattern
