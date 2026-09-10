from uuid import uuid4
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Context, Execution, Feedback, GestureObservation, GesturePattern
from ..schemas import InferenceResult
from .action_catalog import action_label
from .action_executor import execute_action
from .gesture_encoder import cosine_similarity


def _score(observation: GestureObservation, pattern: GesturePattern) -> tuple[float, float]:
    """Return the pattern's confidence weighted by gesture shape, and the raw similarity."""
    similarity = cosine_similarity(observation.gesture_embedding, pattern.gesture_embedding)
    key_bonus = 1.0 if observation.gesture_key == pattern.gesture_key else 0.0
    shape_score = (0.20 * key_bonus) + (0.80 * max(similarity, 0.0))
    return round(pattern.confidence * shape_score, 3), similarity


def infer_intent(
    db: Session, observation: GestureObservation, context: Context
) -> InferenceResult:
    # A detection error must not damage a valid action mapping. Temporarily
    # suppress similar detections in this user's activity using the event itself.
    accidental_embeddings = db.scalars(
        select(GestureObservation.gesture_embedding)
        .join(Execution, Execution.observation_id == GestureObservation.id)
        .join(Feedback, Feedback.execution_id == Execution.id)
        .join(Context, Context.id == GestureObservation.context_id)
        .where(
            Feedback.user_id == observation.user_id,
            Feedback.feedback_type == "ACCIDENTAL_GESTURE",
            Feedback.created_at >= datetime.now(timezone.utc) - timedelta(minutes=5),
            Context.activity == context.activity,
        )
    )
    if any(cosine_similarity(observation.gesture_embedding, item) >= 0.95
           for item in accidental_embeddings):
        return InferenceResult(
            matched=False, reason="최근 우발적 동작으로 표시한 유사 모션은 5분간 실행하지 않습니다."
        )
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

    scored = sorted((item for item in scored if item[1] >= 0.85), key=lambda item: item[0], reverse=True)
    if not scored:
        return InferenceResult(matched=False, reason="모션 특징이 승인된 기억과 충분히 유사하지 않아 실행하지 않았습니다.")
    confidence, similarity, pattern = scored[0]
    if any(other.intent != pattern.intent and confidence - score < 0.08
           for score, _, other in scored[1:]):
        return InferenceResult(matched=False, confidence=confidence,
                               reason="서로 다른 의도의 점수가 비슷하여 실행하지 않았습니다.")
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
