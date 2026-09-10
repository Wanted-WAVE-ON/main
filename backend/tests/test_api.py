USER = "demo-user"


def observe(client, activity="presentation", active_app="PowerPoint", direction="right"):
    response = client.post(
        "/api/v1/observe",
        json={
            "user_id": USER,
            "context": {
                "active_app": active_app,
                "activity": activity,
                "space": "test_space",
                "device": "laptop",
            },
            "gesture": {
                "motion_type": "swipe",
                "direction": direction,
                "duration_ms": 430,
            },
            "attempt_inference": True,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def teach(client, observation_id, intent, target):
    response = client.post(
        "/api/v1/teach",
        json={
            "user_id": USER,
            "observation_id": observation_id,
            "action_type": intent,
            "target": target,
            "parameters": {},
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def respond(client, suggestion_id, decision, modified_intent=None, expect=200):
    response = client.post(
        f"/api/v1/suggestions/{suggestion_id}/respond",
        json={"decision": decision, "modified_intent": modified_intent},
    )
    assert response.status_code == expect, response.text
    return response.json()


def feedback(client, execution_id, feedback_type, corrected_intent=None, expect=200):
    response = client.post(
        f"/api/v1/executions/{execution_id}/feedback",
        json={
            "user_id": USER,
            "feedback_type": feedback_type,
            "corrected_intent": corrected_intent,
        },
    )
    assert response.status_code == expect, response.text
    return response.json()


def dashboard(client):
    return client.get("/api/v1/dashboard", params={"user_id": USER}).json()


def train_until_suggested(client, activity, app, intent, target, rounds=3):
    suggestion = None
    for _ in range(rounds):
        event = observe(client, activity=activity, active_app=app)
        result = teach(client, event["observation"]["id"], intent, target)
        suggestion = result.get("suggestion")
    assert suggestion is not None
    assert suggestion["status"] == "PENDING"
    return suggestion


def train_and_accept(client, activity, app, intent, target):
    suggestion = train_until_suggested(client, activity, app, intent, target)
    pattern = respond(client, suggestion["id"], "ACCEPTED")["pattern"]
    assert pattern["status"] == "ACTIVE"
    return pattern


def test_health_and_privacy(client):
    assert client.get("/health").json()["status"] == "ok"
    # The UI labels intents with this map instead of keeping its own copy.
    demo = client.post("/api/v1/demo/bootstrap").json()
    assert demo["intent_labels"]["NEXT_SLIDE"] == "다음 슬라이드"
    privacy = client.get("/api/v1/demo/privacy").json()
    assert privacy["raw_video_stored"] is False
    assert privacy["face_recognition_used"] is False
    assert privacy["cloud_video_uploaded"] is False


def test_static_assets_are_revalidated(client):
    # Without this the browser guesses a freshness window and can serve a stale
    # app.js on the demo machine.
    assert client.get("/static/app.js").headers["cache-control"] == "no-cache"


def test_learning_loop_suggest_accept_execute(client):
    pattern = train_and_accept(
        client,
        activity="presentation",
        app="PowerPoint",
        intent="NEXT_SLIDE",
        target="powerpoint",
    )
    assert pattern["observation_count"] == 3
    assert pattern["auto_execute"] is True
    assert pattern["confidence"] >= 0.85

    inferred = observe(client, activity="presentation", active_app="PowerPoint")
    assert inferred["inference"]["matched"] is True
    assert inferred["inference"]["intent"] == "NEXT_SLIDE"
    assert inferred["inference"]["execution"]["status"] == "SIMULATED"


def test_same_gesture_changes_with_context(client):
    train_and_accept(client, "presentation", "PowerPoint", "NEXT_SLIDE", "powerpoint")
    train_and_accept(client, "music", "Spotify", "NEXT_TRACK", "media_player")

    presentation = observe(client, "presentation", "PowerPoint")
    music = observe(client, "music", "Spotify")
    assert presentation["inference"]["intent"] == "NEXT_SLIDE"
    assert music["inference"]["intent"] == "NEXT_TRACK"

    memories = client.get(
        "/api/v1/memories",
        params={
            "user_id": USER,
            "gesture_key": "swipe:right",
            "context_scope": "music",
        },
    ).json()
    assert [memory["intent"] for memory in memories] == ["NEXT_TRACK"]
    assert dashboard(client)["context"]["activity"] == "music"


def test_wrong_feedback_lowers_confidence(client):
    train_and_accept(client, "presentation", "PowerPoint", "NEXT_SLIDE", "powerpoint")
    inferred = observe(client, "presentation", "PowerPoint")
    execution = inferred["inference"]["execution"]
    before = execution["confidence"]

    after = feedback(client, execution["id"], "WRONG_ACTION")["pattern"]
    assert 0.60 <= after["confidence"] < before
    assert after["status"] == "ACTIVE"

    feedback(client, execution["id"], "WRONG_ACTION", expect=400)

    inferred_again = observe(client, activity="presentation", active_app="PowerPoint")
    assert inferred_again["inference"]["matched"] is True
    second_execution = inferred_again["inference"]["execution"]
    demoted = feedback(client, second_execution["id"], "WRONG_ACTION")["pattern"]
    assert demoted["confidence"] < 0.60
    assert demoted["status"] == "CANDIDATE"
    assert demoted["auto_execute"] is False
    no_execution = observe(client, activity="presentation", active_app="PowerPoint")
    assert no_execution["inference"]["matched"] is False


def test_observation_never_accepts_or_returns_raw_frame(client):
    result = observe(client)
    observation = result["observation"]
    assert observation["frame_stored"] is False
    assert "frame" not in observation
    assert "image" not in observation

    rejected = client.post(
        "/api/v1/observe",
        json={
            "user_id": USER,
            "context": {"active_app": "PowerPoint", "activity": "presentation"},
            "gesture": {"motion_type": "swipe", "direction": "right", "image": "raw"},
            "frame": "raw",
        },
    )
    assert rejected.status_code == 422


def test_unsupported_context_is_rejected_without_creating_data(client):
    response = client.post(
        "/api/v1/observe",
        json={
            "user_id": USER,
            "context": {"active_app": "Browser", "activity": "browser"},
            "gesture": {"motion_type": "swipe", "direction": "right"},
        },
    )
    assert response.status_code == 422
    state = dashboard(client)
    assert state["context"] is None
    assert state["counts"]["observations"] == 0


def test_tied_intents_withdraw_pending_suggestion(client):
    train_until_suggested(
        client, "presentation", "PowerPoint", "NEXT_SLIDE", "powerpoint"
    )
    for _ in range(3):
        event = observe(client)
        result = teach(client, event["observation"]["id"], "PREVIOUS_SLIDE", "powerpoint")

    assert result["suggestion"] is None
    pending = client.get(
        "/api/v1/suggestions", params={"user_id": USER, "status": "PENDING"}
    ).json()
    assert pending == []


def test_tied_intents_suspend_active_memory(client):
    train_and_accept(client, "presentation", "PowerPoint", "NEXT_SLIDE", "powerpoint")
    for _ in range(3):
        event = observe(client)
        result = teach(client, event["observation"]["id"], "PREVIOUS_SLIDE", "powerpoint")

    assert result["pattern"]["status"] == "CANDIDATE"
    assert result["pattern"]["auto_execute"] is False
    unmatched = observe(client)
    assert unmatched["inference"]["matched"] is False
    recovered = teach(
        client, unmatched["observation"]["id"], "NEXT_SLIDE", "powerpoint"
    )
    assert recovered["suggestion"]["status"] == "PENDING"


def test_suggestion_can_be_modified(client):
    suggestion = train_until_suggested(
        client, "presentation", "PowerPoint", "NEXT_SLIDE", "powerpoint"
    )

    pattern = respond(client, suggestion["id"], "MODIFIED", "PREVIOUS_SLIDE")["pattern"]
    assert pattern["intent"] == "PREVIOUS_SLIDE"
    assert pattern["status"] == "ACTIVE"


def test_accepting_relearned_intent_deactivates_modified_memory(client):
    suggestion = train_until_suggested(
        client, "presentation", "PowerPoint", "NEXT_SLIDE", "powerpoint"
    )
    respond(client, suggestion["id"], "MODIFIED", "PREVIOUS_SLIDE")

    event = observe(client)
    relearned = teach(
        client, event["observation"]["id"], "NEXT_SLIDE", "powerpoint"
    )["suggestion"]
    respond(client, relearned["id"], "ACCEPTED")

    memories = client.get("/api/v1/memories", params={"user_id": USER}).json()
    assert [memory["intent"] for memory in memories] == ["NEXT_SLIDE"]


def test_suggestion_rejects_intent_from_another_context(client):
    observation_id = observe(client)["observation"]["id"]
    invalid_teach = client.post(
        "/api/v1/teach",
        json={
            "user_id": USER,
            "observation_id": observation_id,
            "action_type": "NEXT_TRACK",
            "target": "media_player",
        },
    )
    assert invalid_teach.status_code == 400
    assert "not allowed" in invalid_teach.json()["detail"]

    suggestion = train_until_suggested(
        client, "presentation", "PowerPoint", "NEXT_SLIDE", "powerpoint"
    )

    rejected = respond(client, suggestion["id"], "MODIFIED", "NEXT_TRACK", expect=400)
    assert "not allowed" in rejected["detail"]


def test_suggestion_rejects_duplicate_modified_intent(client):
    train_and_accept(client, "presentation", "PowerPoint", "NEXT_SLIDE", "powerpoint")
    suggestion = train_until_suggested(
        client, "presentation", "PowerPoint", "PREVIOUS_SLIDE", "powerpoint", rounds=4
    )

    rejected = respond(client, suggestion["id"], "MODIFIED", "NEXT_SLIDE", expect=400)
    assert "already exists" in rejected["detail"]


def test_feedback_rejects_intent_from_another_context(client):
    train_and_accept(client, "presentation", "PowerPoint", "NEXT_SLIDE", "powerpoint")
    execution = observe(client)["inference"]["execution"]

    rejected = feedback(client, execution["id"], "WRONG_ACTION", "NEXT_TRACK", expect=400)
    assert "not allowed" in rejected["detail"]

    inferred = observe(client)
    assert inferred["inference"]["intent"] == "NEXT_SLIDE"


def test_feedback_rejects_duplicate_corrected_intent(client):
    train_and_accept(client, "presentation", "PowerPoint", "NEXT_SLIDE", "powerpoint")
    suggestion = train_until_suggested(
        client, "presentation", "PowerPoint", "PREVIOUS_SLIDE", "powerpoint", rounds=4
    )
    respond(client, suggestion["id"], "ACCEPTED")
    execution = observe(client)["inference"]["execution"]

    rejected = feedback(client, execution["id"], "WRONG_ACTION", "NEXT_SLIDE", expect=400)
    assert "already exists" in rejected["detail"]


def test_os_execution_is_blocked_when_target_app_is_not_active(monkeypatch):
    """FR-10: a real key press only goes out while the target app is frontmost."""
    from silent_orchestra.config import settings
    from silent_orchestra.services import action_executor

    monkeypatch.setattr(settings, "enable_os_actions", True)
    monkeypatch.setattr(settings, "require_active_window", True)

    def pressed_key(_key):
        raise AssertionError("a key was sent while the target app was not active")

    monkeypatch.setattr(action_executor, "active_window", lambda: "Slack")
    mode, status, error = action_executor.execute_action("NEXT_SLIDE", "powerpoint")
    assert (mode, status) == ("OS", "FAILED")
    assert "Slack" in error

    # An unreportable window (no accessibility permission) is also a refusal.
    monkeypatch.setattr(action_executor, "active_window", lambda: None)
    assert action_executor.execute_action("NEXT_SLIDE", "powerpoint")[1] == "FAILED"

    # The matching app passes the check and reaches the key press.
    monkeypatch.setattr(action_executor, "active_window", lambda: "Microsoft PowerPoint")
    assert action_executor.check_active_window("powerpoint") is None

    # Skipping the check is opt-in.
    monkeypatch.setattr(settings, "require_active_window", False)
    monkeypatch.setattr(action_executor, "active_window", pressed_key)
    assert action_executor.execute_action("NEXT_SLIDE", "powerpoint")[0] == "OS"


def test_macos_active_window_merges_the_window_title(monkeypatch):
    """FR-10: on macOS only the title says "Google Slides"; without permission the name remains."""
    import platform

    from silent_orchestra.services import action_executor

    monkeypatch.setattr(platform, "system", lambda: "Darwin")

    def osascript(script):
        if "front window" in script:
            return "Demo - Google Slides - Google Chrome"
        return "Google Chrome"

    monkeypatch.setattr(action_executor, "_osascript", osascript)
    assert action_executor.check_active_window("powerpoint") is None

    def denied(script):
        if "front window" in script:
            raise RuntimeError("-1719 accessibility permission denied")
        return "Google Chrome"

    monkeypatch.setattr(action_executor, "_osascript", denied)
    assert action_executor.active_window() == "Google Chrome"


def test_failed_execution_is_visible_as_failed_in_the_dashboard(client, monkeypatch):
    """FR-15: the dashboard separates a failed execution from a successful one."""
    from silent_orchestra.services import intent_reasoner

    train_and_accept(client, "presentation", "PowerPoint", "NEXT_SLIDE", "powerpoint")
    monkeypatch.setattr(
        intent_reasoner, "execute_action", lambda *_: ("OS", "FAILED", "대상 앱이 활성 상태가 아닙니다.")
    )
    result = observe(client)
    assert result["inference"]["execution"]["status"] == "FAILED"

    events = dashboard(client)["events"]
    execution_event = next(event for event in events if event["type"] == "execution")
    assert execution_event["status"] == "FAILED"
    assert "활성 상태가 아닙니다" in execution_event["detail"]


def test_reset_clears_learned_data_and_relearning_works(client):
    """FR-16: reset erases dependent rows, and the loop can be trained again after it."""
    train_and_accept(client, "presentation", "PowerPoint", "NEXT_SLIDE", "powerpoint")
    assert observe(client)["inference"]["matched"] is True

    assert client.post("/api/v1/demo/reset").status_code == 200
    state = dashboard(client)
    assert state["counts"] == {
        "observations": 0,
        "learned_memories": 0,
        "pending_suggestions": 0,
        "feedback": 0,
    }
    assert state["events"] == []

    train_and_accept(client, "presentation", "PowerPoint", "NEXT_SLIDE", "powerpoint")
    assert observe(client)["inference"]["matched"] is True


def test_reset_failure_rolls_back_with_no_partial_deletion(client, monkeypatch):
    """FR-16 AC-FR-16-02: a failure mid-reset leaves the prior state fully intact."""
    import pytest
    from sqlalchemy.orm import Session

    train_and_accept(client, "presentation", "PowerPoint", "NEXT_SLIDE", "powerpoint")
    before = client.get("/api/v1/dashboard?user_id=demo-user").json()
    assert before["counts"]["learned_memories"] == 1
    assert before["counts"]["observations"] > 0

    # Fail after the demo user (and its cascaded rows) have been deleted and
    # flushed, but before the replacement user is persisted.
    def failing_add(self, *args, **kwargs):
        raise RuntimeError("simulated failure after cascade delete")

    monkeypatch.setattr(Session, "add", failing_add)
    with pytest.raises(RuntimeError):
        client.post("/api/v1/demo/reset")
    monkeypatch.undo()

    after = client.get("/api/v1/dashboard?user_id=demo-user").json()
    assert "counts" in after, "demo user was partially deleted despite the failure"
    assert after["counts"] == before["counts"]
    assert after["events"] == before["events"]

    # The session is not wedged: a real reset still succeeds afterwards.
    assert client.post("/api/v1/demo/reset").status_code == 200
    assert client.get("/api/v1/dashboard?user_id=demo-user").json()["counts"] == {
        "observations": 0,
        "learned_memories": 0,
        "pending_suggestions": 0,
        "feedback": 0,
    }


def test_reset_is_refused_outside_demo_mode(client, monkeypatch):
    """FR-16: reset is a demo-only affordance."""
    from silent_orchestra.config import settings

    train_and_accept(client, "presentation", "PowerPoint", "NEXT_SLIDE", "powerpoint")
    monkeypatch.setattr(settings, "demo_mode", False)

    assert client.post("/api/v1/demo/reset").status_code == 403
    assert dashboard(client)["counts"]["learned_memories"] == 1


def test_reset_counts_all_demo_rows_preserves_other_user_and_relearns(client, db_session):
    from sqlalchemy import func, select
    from silent_orchestra.models import (
        User, Context, GestureObservation, Action, GesturePattern,
        AgentSuggestion, Execution, Feedback,
    )
    models = (Context, GestureObservation, Action, GesturePattern, AgentSuggestion, Execution, Feedback)
    train_and_accept(client, "presentation", "PowerPoint", "NEXT_SLIDE", "powerpoint")
    execution = observe(client)["inference"]["execution"]
    feedback(client, execution["id"], "CORRECT")
    db_session.add(User(id="other-user", name="Other"))
    db_session.commit()
    payload = {"user_id": "other-user", "context": {"activity": "music", "active_app": "Spotify"},
               "gesture": {"motion_type": "swipe", "direction": "left"}}
    assert client.post("/api/v1/observe", json=payload).status_code == 200
    before_other = client.get("/api/v1/dashboard?user_id=other-user").json()
    expected = {model.__tablename__: db_session.scalar(select(func.count()).select_from(model).where(model.user_id == USER)) for model in models}
    assert all(count > 0 for count in expected.values())
    result = client.post("/api/v1/demo/reset")
    assert result.status_code == 200
    assert result.json()["deleted_counts"] == expected
    for model in models:
        assert db_session.scalar(select(func.count()).select_from(model).where(model.user_id == USER)) == 0
    assert client.get("/api/v1/dashboard?user_id=other-user").json() == before_other
    assert dashboard(client)["context"] is None
    for attempt in range(1, 4):
        event = observe(client)
        learned = teach(client, event["observation"]["id"], "NEXT_SLIDE", "powerpoint")
        assert learned["progress_current"] == attempt
        assert (learned["suggestion"] is not None) == (attempt == 3)


def test_reset_commit_failure_restores_every_table(client, db_session, monkeypatch):
    import pytest
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from silent_orchestra.models import User, Context, GestureObservation, Action, GesturePattern, AgentSuggestion, Execution, Feedback
    models = (User, Context, GestureObservation, Action, GesturePattern, AgentSuggestion, Execution, Feedback)
    train_and_accept(client, "presentation", "PowerPoint", "NEXT_SLIDE", "powerpoint")
    feedback(client, observe(client)["inference"]["execution"]["id"], "CORRECT")
    def snapshot():
        return {model.__tablename__: set(db_session.scalars(select(model.id)).all()) for model in models}
    before = snapshot()
    def fail_commit(self):
        self.flush()
        raise RuntimeError("commit failed after recreation")
    with monkeypatch.context() as patch:
        patch.setattr(Session, "commit", fail_commit)
        with pytest.raises(RuntimeError):
            client.post("/api/v1/demo/reset")
    assert snapshot() == before
    assert client.post("/api/v1/demo/reset").status_code == 200


def test_privacy_openapi_observe_contract_is_closed(client):
    schema = client.get("/openapi.json").json()
    request_schema = schema["paths"]["/api/v1/observe"]["post"]["requestBody"]["content"]["application/json"]["schema"]
    assert request_schema["$ref"].endswith("/ObserveRequest")
    expected = {
        "ObserveRequest": {"user_id", "context", "gesture", "attempt_inference"},
        "ContextInput": {"active_app", "activity", "space", "device"},
        "GestureInput": {"motion_type", "direction", "duration_ms", "embedding", "speed", "amplitude"},
    }
    for name, fields in expected.items():
        model = schema["components"]["schemas"][name]
        assert model["additionalProperties"] is False
        assert set(model["properties"]) == fields
    embedding = schema["components"]["schemas"]["GestureInput"]["properties"]["embedding"]
    array = next(item for item in embedding["anyOf"] if item["type"] == "array")
    assert array["items"]["type"] == "number"


def test_privacy_rejects_each_raw_field_without_writing_data(client):
    import copy
    payload = {"user_id": USER, "context": {"active_app": "PowerPoint", "activity": "presentation"},
               "gesture": {"motion_type": "swipe", "direction": "right"}}
    before = dashboard(client)
    for location in (None, "context", "gesture"):
        for field in ("frame", "image", "video", "face", "face_embedding", "frame_stored"):
            invalid = copy.deepcopy(payload)
            target = invalid if location is None else invalid[location]
            target[field] = True if field == "frame_stored" else "raw-data"
            response = client.post("/api/v1/observe", json=invalid)
            assert response.status_code == 422, (location, field, response.text)
    assert dashboard(client) == before


def test_privacy_db_rejects_raw_frame_insert_and_update(client, db_engine):
    import pytest
    from sqlalchemy import inspect
    from sqlalchemy.exc import IntegrityError
    observation = observe(client)["observation"]
    with db_engine.connect() as connection:
        row = connection.exec_driver_sql(
            "SELECT frame_stored FROM gesture_observations WHERE id = ?", (observation["id"],)
        ).one()
        assert row[0] == 0
    columns = inspect(db_engine).get_columns("gesture_observations")
    assert {column["name"] for column in columns} == {
        "id", "user_id", "context_id", "gesture_key", "gesture_embedding",
        "motion_type", "direction", "duration_ms", "frame_stored", "detected_at",
    }
    assert not any("BLOB" in str(column["type"]).upper() for column in columns)
    statements = [
        ("UPDATE gesture_observations SET frame_stored = 1 WHERE id = ?", (observation["id"],)),
        ("""INSERT INTO gesture_observations
            (id, user_id, context_id, gesture_key, gesture_embedding, motion_type, direction, duration_ms, frame_stored, detected_at)
            SELECT 'forbidden-frame', user_id, context_id, gesture_key, gesture_embedding, motion_type, direction, duration_ms, 1, detected_at
            FROM gesture_observations WHERE id = ?""", (observation["id"],)),
    ]
    for sql, parameters in statements:
        with pytest.raises(IntegrityError, match="ck_raw_frame_never_stored"):
            with db_engine.begin() as connection:
                connection.exec_driver_sql(sql, parameters)
    assert dashboard(client)["counts"]["observations"] == 1
