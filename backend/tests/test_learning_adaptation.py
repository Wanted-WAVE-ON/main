from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

from silent_orchestra.models import Action, AgentSuggestion, GesturePattern
from test_api import USER, feedback, observe, respond, teach


def record(client, intent="NEXT_SLIDE", target="powerpoint", embedding=None):
    gesture = {"motion_type": "swipe", "direction": "right", "duration_ms": 430}
    if embedding is not None:
        gesture["embedding"] = embedding
    response = client.post(
        "/api/v1/observe",
        json={
            "user_id": USER,
            "context": {"activity": "presentation", "active_app": "PowerPoint"},
            "gesture": gesture,
            "attempt_inference": False,
        },
    )
    assert response.status_code == 200, response.text
    return teach(client, response.json()["observation"]["id"], intent, target)


def train(client, rounds=3, **kwargs):
    result = None
    for _ in range(rounds):
        result = record(client, **kwargs)
    return result


def pending(client):
    response = client.get("/api/v1/suggestions", params={"user_id": USER, "status": "PENDING"})
    assert response.status_code == 200
    return response.json()


def test_recent_window_switches_active_winner_without_passing_through_a_tie(client, db_session):
    learned = train(client, rounds=10)
    old_id = respond(client, learned["suggestion"]["id"], "ACCEPTED")["pattern"]["id"]
    train(client, rounds=9, intent="PREVIOUS_SLIDE")
    record(client, intent="START_PRESENTATION")
    assert db_session.get(GesturePattern, old_id).status == "ACTIVE"

    # The 21st action evicts the oldest NEXT_SLIDE: 10/9/1 becomes 9/10/1.
    # No tied update occurs, so tie-only demotion would leave both intents live.
    result = record(client, intent="PREVIOUS_SLIDE")
    assert result["pattern"]["intent"] == "PREVIOUS_SLIDE"
    assert result["pattern"]["observation_count"] == 10
    assert result["pattern"]["confidence"] == pytest.approx(0.96)
    assert result["suggestion"]["status"] == "PENDING"
    db_session.expire_all()
    old_pattern = db_session.get(GesturePattern, old_id)
    assert (old_pattern.status, old_pattern.auto_execute) == ("CANDIDATE", False)
    assert client.get("/api/v1/memories", params={"user_id": USER}).json() == []


def test_expired_evidence_no_longer_overrules_new_habit(client, db_session):
    learned = train(client)
    old_id = respond(client, learned["suggestion"]["id"], "ACCEPTED")["pattern"]["id"]
    db_session.execute(update(Action).values(executed_at=datetime.now(timezone.utc) - timedelta(days=31)))
    db_session.commit()

    result = record(client, intent="PREVIOUS_SLIDE")
    assert result["pattern"]["intent"] == "PREVIOUS_SLIDE"
    assert result["pattern"]["observation_count"] == 1
    assert result["pattern"]["confidence"] == pytest.approx(0.67)
    assert result["suggestion"] is None
    old_pattern = db_session.get(GesturePattern, old_id)
    assert (old_pattern.status, old_pattern.auto_execute) == ("CANDIDATE", False)


def test_expired_support_withdraws_pending_suggestion_below_threshold(client, db_session):
    learned = train(client)
    suggestion_id = learned["suggestion"]["id"]
    db_session.execute(update(Action).values(executed_at=datetime.now(timezone.utc) - timedelta(days=31)))
    db_session.commit()

    result = record(client)
    assert result["pattern"]["observation_count"] == 1
    assert result["suggestion"] is None
    assert pending(client) == []
    assert db_session.get(AgentSuggestion, suggestion_id) is None


def test_pending_suggestion_tracks_current_confidence_and_evidence(client):
    learned = train(client)
    original = learned["suggestion"]
    updated = record(client)["suggestion"]
    assert updated["id"] == original["id"]
    assert updated["confidence"] > original["confidence"]
    assert "4회" in updated["reason"]

    less_consistent = record(client, intent="PREVIOUS_SLIDE")
    assert less_consistent["suggestion"]["id"] == original["id"]
    assert less_consistent["suggestion"]["confidence"] == less_consistent["pattern"]["confidence"]
    assert less_consistent["suggestion"]["confidence"] < updated["confidence"]
    assert len(pending(client)) == 1


def test_rejection_requires_fresh_matching_actions_after_each_rejection(client, db_session):
    learned = train(client)
    suggestion_id = learned["suggestion"]["id"]
    for _ in range(2):
        rejected = respond(client, suggestion_id, "REJECTED")
        assert rejected["pattern"]["status"] == "REJECTED"
        record(client, intent="PREVIOUS_SLIDE")  # A different action is not fresh support.
        for _ in range(2):
            suppressed = record(client)
            assert suppressed["pattern"]["status"] == "REJECTED"
            assert suppressed["suggestion"] is None
            assert pending(client) == []
        proposed = record(client)
        assert proposed["pattern"]["status"] == "CANDIDATE"
        assert proposed["suggestion"]["id"] != suggestion_id
        suggestion_id = proposed["suggestion"]["id"]

    rejections = db_session.scalars(
        select(AgentSuggestion).where(AgentSuggestion.status == "REJECTED")
    ).all()
    assert len(rejections) == 2
    assert all(item.responded_at is not None for item in rejections)


def test_target_uses_winner_mode_and_most_recent_value_to_break_ties(client):
    record(client, target="first_target")
    record(client, target="second_target")
    mode = record(client, target="second_target")
    assert mode["pattern"]["target"] == "second_target"
    tied = record(client, target="first_target")
    assert tied["pattern"]["target"] == "first_target"
    loser = record(client, intent="PREVIOUS_SLIDE", target="unrelated_target")
    assert loser["pattern"]["target"] == "first_target"


def test_centroid_uses_only_recent_winner_observations_and_latest_dimension(client):
    record(client, embedding=[1, 0, 0, 0, 0, 0])
    record(client, embedding=[0, 1, 0, 0, 0, 0])
    record(client, embedding=[0, 0, 1, 0, 0, 0])
    loser = record(client, intent="PREVIOUS_SLIDE", embedding=[9, 9, 9, 9, 9, 9])
    assert loser["pattern"]["gesture_embedding"] == pytest.approx([1 / 3] * 3 + [0] * 3, abs=1e-6)

    measured = [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    migrated = record(client, embedding=measured)
    assert migrated["pattern"]["gesture_embedding"] == measured
    next_loser = record(client, intent="PREVIOUS_SLIDE", embedding=[0, 1, 0, 0, 0, 0])
    assert next_loser["pattern"]["gesture_embedding"] == measured
    assert next_loser["pattern"]["observation_count"] == 4


def test_agent_actions_cannot_reinforce_their_own_mapping(client, db_session):
    train(client)
    db_session.execute(update(Action).values(executed_by="AGENT"))
    db_session.commit()
    result = record(client, intent="PREVIOUS_SLIDE")
    assert result["pattern"]["intent"] == "PREVIOUS_SLIDE"
    assert result["pattern"]["observation_count"] == 1
    assert result["suggestion"] is None
    assert pending(client) == []


def test_accidental_detection_feedback_preserves_the_mapping(client):
    learned = train(client)
    accepted = respond(client, learned["suggestion"]["id"], "ACCEPTED")["pattern"]
    execution = observe(client)["inference"]["execution"]
    result = feedback(client, execution["id"], "ACCIDENTAL_GESTURE")
    pattern = result["pattern"]
    assert result["feedback"]["feedback_type"] == "ACCIDENTAL_GESTURE"
    assert pattern["confidence"] == accepted["confidence"]
    assert pattern["negative_feedback_count"] == accepted["negative_feedback_count"]
    assert (pattern["status"], pattern["auto_execute"]) == ("ACTIVE", True)
