PRAGMA foreign_key_check;

SELECT CASE WHEN COUNT(*) = 8 THEN 1 ELSE 0 END AS assert_eight_core_tables
FROM sqlite_master
WHERE type = 'table'
  AND name IN (
    'users', 'contexts', 'gesture_observations', 'actions',
    'gesture_patterns', 'agent_suggestions', 'executions', 'feedback'
  );

SELECT CASE WHEN COUNT(*) = 0 THEN 1 ELSE 0 END AS assert_no_raw_frames
FROM gesture_observations
WHERE frame_stored <> 0;

SELECT CASE WHEN COUNT(*) = 2 THEN 1 ELSE 0 END AS assert_context_specific_memories
FROM personal_gesture_memory
WHERE user_id = 'user-demo'
  AND gesture_key = 'swipe:right'
  AND context_scope IN ('presentation', 'music');

SELECT CASE WHEN COUNT(DISTINCT intent) = 2 THEN 1 ELSE 0 END AS assert_same_gesture_different_intents
FROM personal_gesture_memory
WHERE user_id = 'user-demo'
  AND gesture_key = 'swipe:right';

SELECT CASE WHEN COUNT(*) = 0 THEN 1 ELSE 0 END AS assert_no_pending_seed_suggestions
FROM agent_suggestions
WHERE status = 'PENDING';

SELECT CASE WHEN COUNT(*) = 1 THEN 1 ELSE 0 END AS assert_execution_feedback_link
FROM executions AS e
JOIN feedback AS f ON f.execution_id = e.id
WHERE e.id = 'exe-ppt-1'
  AND f.feedback_type = 'CORRECT';
