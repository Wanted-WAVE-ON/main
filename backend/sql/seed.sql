INSERT INTO users (id, name) VALUES
('user-demo', '나영');

INSERT INTO contexts (id, user_id, active_app, activity, space, device) VALUES
('ctx-ppt-1', 'user-demo', 'PowerPoint', 'presentation', 'meeting_room', 'laptop'),
('ctx-music-1', 'user-demo', 'Spotify', 'music', 'desk', 'laptop');

INSERT INTO gesture_observations (
    id, user_id, context_id, gesture_key, gesture_embedding,
    motion_type, direction, duration_ms, frame_stored
) VALUES
('obs-ppt-1', 'user-demo', 'ctx-ppt-1', 'swipe:right', '[0.69,0,0.69,0,0,0.15]', 'swipe', 'right', 430, 0),
('obs-music-1', 'user-demo', 'ctx-music-1', 'swipe:right', '[0.69,0,0.69,0,0,0.15]', 'swipe', 'right', 420, 0);

INSERT INTO actions (
    id, user_id, observation_id, action_type, target, parameters, executed_by
) VALUES
('act-ppt-1', 'user-demo', 'obs-ppt-1', 'NEXT_SLIDE', 'powerpoint', '{}', 'USER'),
('act-music-1', 'user-demo', 'obs-music-1', 'NEXT_TRACK', 'media_player', '{}', 'USER');

INSERT INTO gesture_patterns (
    id, user_id, gesture_key, gesture_embedding, motion_type, direction,
    intent, context_scope, target, confidence, observation_count,
    auto_execute, status
) VALUES
('pat-ppt-right', 'user-demo', 'swipe:right', '[0.69,0,0.69,0,0,0.15]', 'swipe', 'right',
 'NEXT_SLIDE', 'presentation', 'powerpoint', 0.94, 12, 1, 'ACTIVE'),
('pat-music-right', 'user-demo', 'swipe:right', '[0.69,0,0.69,0,0,0.15]', 'swipe', 'right',
 'NEXT_TRACK', 'music', 'media_player', 0.91, 8, 1, 'ACTIVE');

INSERT INTO agent_suggestions (
    id, user_id, gesture_pattern_id, suggested_intent, reason, confidence, status, responded_at
) VALUES
('sug-ppt-right', 'user-demo', 'pat-ppt-right', 'NEXT_SLIDE',
 'presentation 상황에서 유사 동작 후 다음 슬라이드 행동이 12회 관찰됨', 0.94, 'ACCEPTED', CURRENT_TIMESTAMP),
('sug-music-right', 'user-demo', 'pat-music-right', 'NEXT_TRACK',
 'music 상황에서 유사 동작 후 다음 트랙 행동이 8회 관찰됨', 0.91, 'ACCEPTED', CURRENT_TIMESTAMP);

INSERT INTO executions (
    id, user_id, gesture_pattern_id, observation_id, intent, target,
    parameters, confidence, execution_mode, status
) VALUES
('exe-ppt-1', 'user-demo', 'pat-ppt-right', 'obs-ppt-1', 'NEXT_SLIDE', 'powerpoint', '{}', 0.94, 'DRY_RUN', 'SIMULATED');

INSERT INTO feedback (
    id, user_id, gesture_pattern_id, execution_id, feedback_type
) VALUES
('fb-ppt-1', 'user-demo', 'pat-ppt-right', 'exe-ppt-1', 'CORRECT');
