PRAGMA foreign_keys = ON;

CREATE TABLE users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE contexts (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    active_app TEXT NOT NULL,
    activity TEXT NOT NULL CHECK (activity IN ('presentation','music')),
    space TEXT NOT NULL DEFAULT 'unspecified',
    device TEXT NOT NULL DEFAULT 'laptop',
    captured_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE gesture_observations (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    context_id TEXT NOT NULL,
    gesture_key TEXT NOT NULL,
    gesture_embedding TEXT NOT NULL CHECK (json_valid(gesture_embedding)),
    motion_type TEXT NOT NULL,
    direction TEXT NOT NULL DEFAULT 'none',
    duration_ms INTEGER NOT NULL CHECK (duration_ms >= 0),
    frame_stored INTEGER NOT NULL DEFAULT 0 CHECK (frame_stored = 0),
    detected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (context_id) REFERENCES contexts(id) ON DELETE CASCADE
);

CREATE TABLE actions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    observation_id TEXT NOT NULL UNIQUE,
    action_type TEXT NOT NULL,
    target TEXT NOT NULL,
    parameters TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(parameters)),
    executed_by TEXT NOT NULL DEFAULT 'USER' CHECK (executed_by IN ('USER','AGENT')),
    executed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (observation_id) REFERENCES gesture_observations(id) ON DELETE CASCADE
);

CREATE TABLE gesture_patterns (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    gesture_key TEXT NOT NULL,
    gesture_embedding TEXT NOT NULL CHECK (json_valid(gesture_embedding)),
    motion_type TEXT NOT NULL,
    direction TEXT NOT NULL,
    intent TEXT NOT NULL,
    context_scope TEXT NOT NULL CHECK (context_scope IN ('presentation','music')),
    target TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0 CHECK (confidence BETWEEN 0 AND 1),
    observation_count INTEGER NOT NULL DEFAULT 0 CHECK (observation_count >= 0),
    positive_feedback_count INTEGER NOT NULL DEFAULT 0 CHECK (positive_feedback_count >= 0),
    negative_feedback_count INTEGER NOT NULL DEFAULT 0 CHECK (negative_feedback_count >= 0),
    auto_execute INTEGER NOT NULL DEFAULT 0 CHECK (auto_execute IN (0,1)),
    status TEXT NOT NULL DEFAULT 'CANDIDATE' CHECK (status IN ('CANDIDATE','ACTIVE','REJECTED')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE (user_id, gesture_key, context_scope, intent)
);

CREATE TABLE agent_suggestions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    gesture_pattern_id TEXT NOT NULL,
    suggested_intent TEXT NOT NULL,
    modified_intent TEXT,
    reason TEXT NOT NULL,
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','ACCEPTED','REJECTED','MODIFIED')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    responded_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (gesture_pattern_id) REFERENCES gesture_patterns(id) ON DELETE CASCADE
);

CREATE TABLE executions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    gesture_pattern_id TEXT NOT NULL,
    observation_id TEXT NOT NULL,
    intent TEXT NOT NULL,
    target TEXT NOT NULL,
    parameters TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(parameters)),
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    execution_mode TEXT NOT NULL DEFAULT 'DRY_RUN' CHECK (execution_mode IN ('DRY_RUN','OS')),
    status TEXT NOT NULL CHECK (status IN ('SIMULATED','SUCCEEDED','FAILED')),
    error_message TEXT,
    executed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (gesture_pattern_id) REFERENCES gesture_patterns(id) ON DELETE CASCADE,
    FOREIGN KEY (observation_id) REFERENCES gesture_observations(id) ON DELETE CASCADE
);

CREATE TABLE feedback (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    gesture_pattern_id TEXT NOT NULL,
    execution_id TEXT NOT NULL UNIQUE,
    feedback_type TEXT NOT NULL CHECK (feedback_type IN ('CORRECT','WRONG_ACTION','ACCIDENTAL_GESTURE','IGNORE')),
    corrected_intent TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (gesture_pattern_id) REFERENCES gesture_patterns(id) ON DELETE CASCADE,
    FOREIGN KEY (execution_id) REFERENCES executions(id) ON DELETE CASCADE
);

CREATE INDEX ix_contexts_user_activity ON contexts(user_id, activity);
CREATE INDEX ix_observations_user_gesture ON gesture_observations(user_id, gesture_key);
CREATE INDEX ix_observations_detected_at ON gesture_observations(detected_at);
CREATE INDEX ix_actions_user_type ON actions(user_id, action_type);
CREATE INDEX ix_patterns_memory_lookup ON gesture_patterns(user_id, context_scope, status);
CREATE INDEX ix_suggestions_user_status ON agent_suggestions(user_id, status);
CREATE INDEX ix_executions_user_time ON executions(user_id, executed_at);
CREATE INDEX ix_feedback_pattern_time ON feedback(gesture_pattern_id, created_at);

CREATE VIEW personal_gesture_memory AS
SELECT
    p.id,
    p.user_id,
    p.gesture_key,
    p.motion_type,
    p.direction,
    p.context_scope,
    p.intent,
    p.target,
    p.confidence,
    p.observation_count,
    p.auto_execute,
    p.updated_at
FROM gesture_patterns AS p
WHERE p.status = 'ACTIVE';
