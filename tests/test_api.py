def bootstrap(client):
    response = client.post("/api/v1/demo/bootstrap")
    assert response.status_code == 200
    return response.json()["user"]


def observe(client, activity="presentation", active_app="PowerPoint", direction="right"):
    response = client.post(
        "/api/v1/observe",
        json={
            "user_id": "demo-user",
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
            "user_id": "demo-user",
            "observation_id": observation_id,
            "action_type": intent,
            "target": target,
            "parameters": {},
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def train_until_suggested(client, activity, app, intent, target):
    suggestion = None
    for _ in range(3):
        event = observe(client, activity=activity, active_app=app)
        result = teach(client, event["observation"]["id"], intent, target)
        suggestion = result.get("suggestion")
    assert suggestion is not None
    assert suggestion["status"] == "PENDING"
    return suggestion


def train_and_accept(client, activity, app, intent, target):
    suggestion = train_until_suggested(client, activity, app, intent, target)
    response = client.post(
        f"/api/v1/suggestions/{suggestion['id']}/respond",
        json={"decision": "ACCEPTED"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["pattern"]["status"] == "ACTIVE"
    return response.json()["pattern"]


def test_health_and_privacy(client):
    assert client.get("/health").json()["status"] == "ok"
    bootstrap(client)
    privacy = client.get("/api/v1/demo/privacy").json()
    assert privacy["raw_video_stored"] is False
    assert privacy["face_recognition_used"] is False
    assert privacy["cloud_video_uploaded"] is False


def test_static_assets_are_revalidated(client):
    # Without this the browser guesses a freshness window and can serve a stale
    # app.js on the demo machine.
    assert client.get("/static/app.js").headers["cache-control"] == "no-cache"


def test_learning_loop_suggest_accept_execute(client):
    bootstrap(client)
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
    bootstrap(client)
    train_and_accept(client, "presentation", "PowerPoint", "NEXT_SLIDE", "powerpoint")
    train_and_accept(client, "music", "Spotify", "NEXT_TRACK", "media_player")

    presentation = observe(client, "presentation", "PowerPoint")
    music = observe(client, "music", "Spotify")
    assert presentation["inference"]["intent"] == "NEXT_SLIDE"
    assert music["inference"]["intent"] == "NEXT_TRACK"

    memories = client.get(
        "/api/v1/memories",
        params={
            "user_id": "demo-user",
            "gesture_key": "swipe:right",
            "context_scope": "music",
        },
    ).json()
    assert [memory["intent"] for memory in memories] == ["NEXT_TRACK"]
    dashboard = client.get("/api/v1/dashboard", params={"user_id": "demo-user"}).json()
    assert dashboard["context"]["activity"] == "music"


def test_wrong_feedback_lowers_confidence(client):
    bootstrap(client)
    train_and_accept(client, "presentation", "PowerPoint", "NEXT_SLIDE", "powerpoint")
    inferred = observe(client, "presentation", "PowerPoint")
    execution = inferred["inference"]["execution"]
    before = execution["confidence"]

    response = client.post(
        f"/api/v1/executions/{execution['id']}/feedback",
        json={"user_id": "demo-user", "feedback_type": "WRONG_ACTION"},
    )
    assert response.status_code == 200, response.text
    after = response.json()["pattern"]
    assert 0.60 <= after["confidence"] < before
    assert after["status"] == "ACTIVE"

    duplicate = client.post(
        f"/api/v1/executions/{execution['id']}/feedback",
        json={"user_id": "demo-user", "feedback_type": "WRONG_ACTION"},
    )
    assert duplicate.status_code == 400

    inferred_again = observe(client, activity="presentation", active_app="PowerPoint")
    assert inferred_again["inference"]["matched"] is True
    second_execution = inferred_again["inference"]["execution"]
    demoted = client.post(
        f"/api/v1/executions/{second_execution['id']}/feedback",
        json={"user_id": "demo-user", "feedback_type": "WRONG_ACTION"},
    ).json()["pattern"]
    assert demoted["confidence"] < 0.60
    assert demoted["status"] == "CANDIDATE"
    assert demoted["auto_execute"] is False
    no_execution = observe(client, activity="presentation", active_app="PowerPoint")
    assert no_execution["inference"]["matched"] is False


def test_observation_never_accepts_or_returns_raw_frame(client):
    bootstrap(client)
    result = observe(client)
    observation = result["observation"]
    assert observation["frame_stored"] is False
    assert "frame" not in observation
    assert "image" not in observation

    rejected = client.post(
        "/api/v1/observe",
        json={
            "user_id": "demo-user",
            "context": {"active_app": "PowerPoint", "activity": "presentation"},
            "gesture": {"motion_type": "swipe", "direction": "right", "image": "raw"},
            "frame": "raw",
        },
    )
    assert rejected.status_code == 422


def test_unsupported_context_is_rejected_without_creating_data(client):
    bootstrap(client)
    response = client.post(
        "/api/v1/observe",
        json={
            "user_id": "demo-user",
            "context": {"active_app": "Browser", "activity": "browser"},
            "gesture": {"motion_type": "swipe", "direction": "right"},
        },
    )
    assert response.status_code == 422
    dashboard = client.get("/api/v1/dashboard", params={"user_id": "demo-user"}).json()
    assert dashboard["context"] is None
    assert dashboard["counts"]["observations"] == 0


def test_tied_intents_withdraw_pending_suggestion(client):
    bootstrap(client)
    train_until_suggested(
        client, "presentation", "PowerPoint", "NEXT_SLIDE", "powerpoint"
    )
    for _ in range(3):
        event = observe(client)
        result = teach(client, event["observation"]["id"], "PREVIOUS_SLIDE", "powerpoint")

    assert result["suggestion"] is None
    pending = client.get(
        "/api/v1/suggestions", params={"user_id": "demo-user", "status": "PENDING"}
    ).json()
    assert pending == []


def test_tied_intents_suspend_active_memory(client):
    bootstrap(client)
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
    bootstrap(client)
    suggestion = train_until_suggested(
        client, "presentation", "PowerPoint", "NEXT_SLIDE", "powerpoint"
    )

    response = client.post(
        f"/api/v1/suggestions/{suggestion['id']}/respond",
        json={"decision": "MODIFIED", "modified_intent": "PREVIOUS_SLIDE"},
    )
    assert response.status_code == 200, response.text
    pattern = response.json()["pattern"]
    assert pattern["intent"] == "PREVIOUS_SLIDE"
    assert pattern["status"] == "ACTIVE"


def test_accepting_relearned_intent_deactivates_modified_memory(client):
    bootstrap(client)
    suggestion = train_until_suggested(
        client, "presentation", "PowerPoint", "NEXT_SLIDE", "powerpoint"
    )
    response = client.post(
        f"/api/v1/suggestions/{suggestion['id']}/respond",
        json={"decision": "MODIFIED", "modified_intent": "PREVIOUS_SLIDE"},
    )
    assert response.status_code == 200, response.text

    event = observe(client)
    relearned = teach(
        client, event["observation"]["id"], "NEXT_SLIDE", "powerpoint"
    )["suggestion"]
    response = client.post(
        f"/api/v1/suggestions/{relearned['id']}/respond",
        json={"decision": "ACCEPTED"},
    )
    assert response.status_code == 200, response.text

    memories = client.get(
        "/api/v1/memories", params={"user_id": "demo-user"}
    ).json()
    assert [memory["intent"] for memory in memories] == ["NEXT_SLIDE"]


def test_suggestion_rejects_intent_from_another_context(client):
    bootstrap(client)
    observation_id = observe(client)["observation"]["id"]
    invalid_teach = client.post(
        "/api/v1/teach",
        json={
            "user_id": "demo-user",
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

    response = client.post(
        f"/api/v1/suggestions/{suggestion['id']}/respond",
        json={"decision": "MODIFIED", "modified_intent": "NEXT_TRACK"},
    )
    assert response.status_code == 400
    assert "not allowed" in response.json()["detail"]


def test_suggestion_rejects_duplicate_modified_intent(client):
    bootstrap(client)
    train_and_accept(client, "presentation", "PowerPoint", "NEXT_SLIDE", "powerpoint")
    suggestion = None
    for _ in range(4):
        event = observe(client)
        suggestion = teach(
            client, event["observation"]["id"], "PREVIOUS_SLIDE", "powerpoint"
        )["suggestion"]

    response = client.post(
        f"/api/v1/suggestions/{suggestion['id']}/respond",
        json={"decision": "MODIFIED", "modified_intent": "NEXT_SLIDE"},
    )
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]


def test_feedback_rejects_intent_from_another_context(client):
    bootstrap(client)
    train_and_accept(client, "presentation", "PowerPoint", "NEXT_SLIDE", "powerpoint")
    execution = observe(client)["inference"]["execution"]

    response = client.post(
        f"/api/v1/executions/{execution['id']}/feedback",
        json={
            "user_id": "demo-user",
            "feedback_type": "WRONG_ACTION",
            "corrected_intent": "NEXT_TRACK",
        },
    )
    assert response.status_code == 400
    assert "not allowed" in response.json()["detail"]

    inferred = observe(client)
    assert inferred["inference"]["intent"] == "NEXT_SLIDE"


def test_feedback_rejects_duplicate_corrected_intent(client):
    bootstrap(client)
    train_and_accept(client, "presentation", "PowerPoint", "NEXT_SLIDE", "powerpoint")
    suggestion = None
    for _ in range(4):
        event = observe(client)
        suggestion = teach(
            client, event["observation"]["id"], "PREVIOUS_SLIDE", "powerpoint"
        )["suggestion"]
    response = client.post(
        f"/api/v1/suggestions/{suggestion['id']}/respond",
        json={"decision": "ACCEPTED"},
    )
    assert response.status_code == 200, response.text
    execution = observe(client)["inference"]["execution"]

    response = client.post(
        f"/api/v1/executions/{execution['id']}/feedback",
        json={
            "user_id": "demo-user",
            "feedback_type": "WRONG_ACTION",
            "corrected_intent": "NEXT_SLIDE",
        },
    )
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]


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


def test_failed_execution_is_visible_as_failed_in_the_dashboard(client, monkeypatch):
    """FR-15: the dashboard separates a failed execution from a successful one."""
    from silent_orchestra.services import intent_reasoner

    bootstrap(client)
    train_and_accept(client, "presentation", "PowerPoint", "NEXT_SLIDE", "powerpoint")
    monkeypatch.setattr(
        intent_reasoner, "execute_action", lambda *_: ("OS", "FAILED", "대상 앱이 활성 상태가 아닙니다.")
    )
    result = observe(client)
    assert result["inference"]["execution"]["status"] == "FAILED"

    events = client.get("/api/v1/dashboard?user_id=demo-user").json()["events"]
    execution_event = next(event for event in events if event["type"] == "execution")
    assert execution_event["status"] == "FAILED"
    assert "활성 상태가 아닙니다" in execution_event["detail"]


def test_reset_clears_learned_data_and_relearning_works(client):
    """FR-16: reset erases dependent rows, and the loop can be trained again after it."""
    bootstrap(client)
    train_and_accept(client, "presentation", "PowerPoint", "NEXT_SLIDE", "powerpoint")
    assert observe(client)["inference"]["matched"] is True

    assert client.post("/api/v1/demo/reset").status_code == 200
    dashboard = client.get("/api/v1/dashboard?user_id=demo-user").json()
    assert dashboard["counts"] == {
        "observations": 0,
        "learned_memories": 0,
        "pending_suggestions": 0,
        "feedback": 0,
    }
    assert dashboard["events"] == []

    train_and_accept(client, "presentation", "PowerPoint", "NEXT_SLIDE", "powerpoint")
    assert observe(client)["inference"]["matched"] is True


def test_reset_failure_rolls_back_with_no_partial_deletion(client, monkeypatch):
    """FR-16 AC-FR-16-02: a failure mid-reset leaves the prior state fully intact."""
    import pytest
    from sqlalchemy.orm import Session

    bootstrap(client)
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

    bootstrap(client)
    train_and_accept(client, "presentation", "PowerPoint", "NEXT_SLIDE", "powerpoint")
    monkeypatch.setattr(settings, "demo_mode", False)

    assert client.post("/api/v1/demo/reset").status_code == 403
    assert client.get("/api/v1/dashboard?user_id=demo-user").json()["counts"]["learned_memories"] == 1
