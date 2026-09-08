from scripts.webcam_gesture_client import action_for_key


def test_space_only_teaches_playback_in_music_context():
    assert action_for_key(ord(" "), "music") == ("TOGGLE_PLAYBACK", "media_player")
    assert action_for_key(ord(" "), "presentation") is None
