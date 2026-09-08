from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Context, Execution, GestureObservation, GesturePattern
from ..schemas import InferenceResult
from .action_catalog import action_label
from .action_executor import execute_action
from .gesture_encoder import cosine_similarity


def _score(observation: GestureObservation, pattern: GesturePattern) -> tuple[float, float]:
    """Return the pattern's confidence weighted by gesture shape, and the raw similarity."""
    similarity = cosine_similarity(observation.gesture_embedding, pattern.gesture_embedding)
    key_bonus = 1.0 if observation.gesture_key == pattern.gesture_key else 0.0
    shape_score = (0.75 * key_bonus) + (0.25 * max(similarity, 0.0))
    return round(pattern.confidence * shape_score, 3), similarity


def infer_intent(
    db: Session, observation: GestureObservation, context: Context
) -> InferenceResult:
    scored = [
        (*_score(observation, pattern), pattern)
        for pattern in db.scalars(
            select(GesturePattern).where(
                GesturePattern.user_id == observation.user_id,
                GesturePattern.context_scope == context.activity,
                GesturePattern.status == "ACTIVE",
                GesturePattern.auto_execute.is_(True),
            )
        )
    ]
    if not scored:
        return InferenceResult(
            matched=False,
            reason="현재 상황에서 활성화된 개인 제스처 기억이 없습니다.",
        )

    confidence, similarity, pattern = max(scored, key=lambda item: item[0])
    if confidence < settings.auto_execution_threshold:
        return InferenceResult(
            matched=False,
            intent=pattern.intent,
            target=pattern.target,
            confidence=confidence,
            reason=(
                f"유사한 기억을 찾았지만 자동 실행 기준 {settings.auto_execution_threshold:.2f}보다 "
                "확신도가 낮아 실행하지 않았습니다."
            ),
        )

    mode, status, error_message = execute_action(pattern.intent, pattern.target)
    execution = Execution(
        id=str(uuid4()),
        user_id=observation.user_id,
        gesture_pattern_id=pattern.id,
        observation_id=observation.id,
        intent=pattern.intent,
        target=pattern.target,
        parameters={},
        confidence=confidence,
        execution_mode=mode,
        status=status,
        error_message=error_message,
    )
    db.add(execution)
    db.commit()

    return InferenceResult(
        matched=True,
        intent=pattern.intent,
        target=pattern.target,
        confidence=confidence,
        reason=(
            f"{context.activity} 맥락의 개인 기억과 {similarity:.0%} 유사하여 "
            f"'{action_label(pattern.intent)}' 의도로 해석했습니다."
        ),
        execution=execution,
    )
