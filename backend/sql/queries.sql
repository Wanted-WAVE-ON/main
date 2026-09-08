-- 1. 현재 상황에 활성화된 Personal Gesture Memory 조회
SELECT
    gesture_key,
    context_scope,
    intent,
    target,
    confidence,
    observation_count
FROM personal_gesture_memory
WHERE user_id = 'user-demo'
  AND context_scope = 'presentation'
ORDER BY confidence DESC;

-- 2. 같은 제스처가 맥락별로 어떻게 달리 해석되는지 확인
SELECT
    gesture_key,
    context_scope,
    intent,
    confidence
FROM personal_gesture_memory
WHERE user_id = 'user-demo'
  AND gesture_key = 'swipe:right'
ORDER BY context_scope;

-- 3. 대기 중인 Agent 제안
SELECT
    s.id,
    p.gesture_key,
    p.context_scope,
    s.suggested_intent,
    s.reason,
    s.confidence
FROM agent_suggestions AS s
JOIN gesture_patterns AS p ON p.id = s.gesture_pattern_id
WHERE s.user_id = 'user-demo'
  AND s.status = 'PENDING'
ORDER BY s.created_at DESC;

-- 4. 최근 실행과 피드백 감사 로그
SELECT
    e.intent,
    e.execution_mode,
    e.status,
    e.confidence,
    f.feedback_type,
    e.executed_at
FROM executions AS e
LEFT JOIN feedback AS f ON f.execution_id = e.id
WHERE e.user_id = 'user-demo'
ORDER BY e.executed_at DESC
LIMIT 20;

-- 5. Privacy 검증: 원본 프레임 저장 건수는 항상 0
SELECT COUNT(*) AS raw_frame_count
FROM gesture_observations
WHERE frame_stored <> 0;
