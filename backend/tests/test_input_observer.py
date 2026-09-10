"""Cross-platform coverage for the observe-mode plumbing.

The native ``WindowsHookAdapter`` (SetWindowsHookExW) still needs a real Windows
session and is verified by hand; everything around it is exercised here.
"""

import threading
import time

import pytest

from silent_orchestra.services import input_observer
from silent_orchestra.services.input_observer import (
    ControlKeyFilter,
    ObservedAction,
    WindowsHookAdapter,
    WindowsInputObserver,
)

RIGHT_ARROW, LETTER_N, PAGE_UP, MEDIA_NEXT = 0x27, 0x4E, 0x21, 0xB0


def handle(key_filter, vk, **overrides):
    call = dict(
        key_down=True, injected=False, modifiers=False,
        active_app="PowerPoint Slide Show", observed_at=1.0, presentation_mode=True,
    )
    call.update(overrides)
    return key_filter.handle(vk, **call)


def test_slideshow_navigation_keys_become_semantic_actions():
    action = handle(ControlKeyFilter(), RIGHT_ARROW)
    assert (action.action_type, action.target, action.activity) == ("NEXT_SLIDE", "powerpoint", "presentation")


def test_media_keys_need_a_music_window():
    action = handle(ControlKeyFilter(), MEDIA_NEXT, active_app="Spotify Premium", presentation_mode=False)
    assert (action.action_type, action.target, action.activity) == ("NEXT_TRACK", "media_player", "music")


def test_navigation_keys_outside_the_slide_show_are_ignored():
    # N in the PowerPoint editor edits the outline; only the slide-show window counts.
    assert handle(ControlKeyFilter(), LETTER_N, active_app="Deck - PowerPoint", presentation_mode=False) is None


def test_injected_modified_and_unsupported_events_are_dropped():
    assert handle(ControlKeyFilter(), RIGHT_ARROW, injected=True) is None
    assert handle(ControlKeyFilter(), RIGHT_ARROW, modifiers=True) is None
    assert handle(ControlKeyFilter(), 0x41) is None  # 'A' is not a control key


def test_held_key_autorepeat_is_collapsed_to_one_action():
    key_filter = ControlKeyFilter()
    assert handle(key_filter, PAGE_UP) is not None
    assert handle(key_filter, PAGE_UP) is None                  # autorepeat, no key-up yet
    assert handle(key_filter, PAGE_UP, key_down=False) is None  # release
    assert handle(key_filter, PAGE_UP) is not None              # a fresh press counts again


class FakeAdapter:
    """Stands in for the native hook: emits a script of actions, then idles."""

    def __init__(self, events):
        self.events = list(events)
        self._stop = threading.Event()
        self.stopped = False

    def run(self, emit, ready):
        ready.set()
        for event in self.events:
            emit(event)
        self._stop.wait(2)

    def stop(self):
        self.stopped = True
        self._stop.set()


def _observed(action, at):
    return ObservedAction(action, "powerpoint", "presentation", "PowerPoint Slide Show", at)


def test_observer_streams_injected_adapter_events_through_drain():
    adapter = FakeAdapter([_observed("NEXT_SLIDE", 1.0), _observed("PREVIOUS_SLIDE", 2.0)])
    observer = WindowsInputObserver(adapter=adapter)
    observer.start()
    try:
        drained: list[ObservedAction] = []
        deadline = time.monotonic() + 2
        while len(drained) < 2 and time.monotonic() < deadline:
            drained.extend(observer.drain())
            time.sleep(0.01)
    finally:
        observer.stop()
    assert [event.action_type for event in drained] == ["NEXT_SLIDE", "PREVIOUS_SLIDE"]
    assert adapter.stopped is True


def test_observer_reports_an_adapter_that_dies_after_starting():
    class DyingAdapter:
        def run(self, emit, ready):
            ready.set()
            time.sleep(0.05)
            raise RuntimeError("hook died")

        def stop(self):
            pass

    observer = WindowsInputObserver(adapter=DyingAdapter())
    observer.start()  # ready fired, so start() returns before the failure
    time.sleep(0.15)
    with pytest.raises(OSError):
        observer.drain()


def test_native_adapter_still_requires_windows(monkeypatch):
    monkeypatch.setattr(input_observer.platform, "system", lambda: "Linux")
    observer = WindowsInputObserver(adapter=WindowsHookAdapter())
    with pytest.raises(OSError):
        observer.start()
