from scripts.webcam_gesture_client import action_for_key


def test_space_only_teaches_playback_in_music_context():
    assert action_for_key(ord(" "), "music") == ("TOGGLE_PLAYBACK", "media_player")
    assert action_for_key(ord(" "), "presentation") is None


import sys
from types import SimpleNamespace

import pytest
import requests
from scripts import webcam_gesture_client as webcam


@pytest.fixture
def np():
    return pytest.importorskip("numpy")


@pytest.mark.parametrize("direction,dx", [("right", 2), ("left", -2)])
def test_only_moving_pixels_determine_direction(direction, dx, np):
    flow = np.zeros((100, 100, 2))
    flow[:2, :, 0] = dx
    assert webcam.horizontal_motion(flow, np.ones((100, 100), dtype=bool)) == (direction, 0.02)


@pytest.mark.parametrize("dx,dy,foreground", [(0, 0, True), (2, 3, True), (2, 0, False)])
def test_static_vertical_and_background_motion_are_ignored(dx, dy, foreground, np):
    flow = np.empty((10, 10, 2))
    flow[:] = (dx, dy)
    assert webcam.horizontal_motion(flow, np.full((10, 10), foreground))[0] is None


def test_small_motion_is_ignored(np):
    flow = np.zeros((100, 100, 2))
    flow[0, 0, 0] = 5
    assert webcam.horizontal_motion(flow, np.ones((100, 100), dtype=bool))[0] is None


def test_feature_payload_observation_contract(client):
    client.post("/api/v1/demo/bootstrap")
    payload = webcam.observation_payload("demo-user", "music", "Spotify", "right")
    assert payload["gesture"] == {"motion_type": "swipe", "direction": "right", "duration_ms": 430}
    assert set(payload) == {"user_id", "context", "gesture", "attempt_inference"}
    response = client.post("/api/v1/observe", json=payload)
    assert response.status_code == 200
    observation = response.json()["observation"]
    assert observation["gesture_key"] == "swipe:right"
    assert observation["frame_stored"] is False
    assert observation["gesture_embedding"]


@pytest.mark.parametrize("opened,read_ok,api_error", [(False, False, False), (True, False, False), (True, False, True)])
def test_failure_releases_camera_and_offers_simulation(monkeypatch, capsys, opened, read_ok, api_error, np):
    released = []
    capture = SimpleNamespace(isOpened=lambda: opened, read=lambda: (read_ok, None), release=lambda: released.append(True))
    fake_cv = SimpleNamespace(VideoCapture=lambda _: capture, createBackgroundSubtractorMOG2=lambda **_: None,
                              destroyAllWindows=lambda: None, error=RuntimeError)
    monkeypatch.setitem(sys.modules, "cv2", fake_cv)
    monkeypatch.setattr(sys, "argv", ["webcam"])
    def post(*_):
        if api_error:
            raise requests.ConnectionError("offline")
        return {}
    monkeypatch.setattr(webcam, "post_json", post)
    assert webcam.main() == 1
    assert released == [True]
    output = capsys.readouterr()
    assert "Stable Simulation" in output.out
    assert "failed" in output.err or "could not be opened" in output.err


@pytest.mark.parametrize("activity,next_action,previous_action", [
    ("music", "NEXT_TRACK", "PREVIOUS_TRACK"),
    ("presentation", "NEXT_SLIDE", "PREVIOUS_SLIDE"),
])
def test_context_navigation_keys(activity, next_action, previous_action):
    assert webcam.action_for_key(ord("n"), activity)[0] == next_action
    assert webcam.action_for_key(ord("b"), activity)[0] == previous_action
