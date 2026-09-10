"""Observe allowlisted application controls without intercepting or retaining text.

The Windows hook always calls CallNextHookEx. Only semantic actions leave the
callback; raw keyboard events and image data are never queued or persisted.
"""

import ctypes
import platform
import queue
import threading
import time
from dataclasses import dataclass
from typing import Callable

from .context_resolver import resolve_context


PRESENTATION_KEYS = {
    0x27: "NEXT_SLIDE", 0x22: "NEXT_SLIDE", 0x4E: "NEXT_SLIDE", 0x20: "NEXT_SLIDE",
    0x25: "PREVIOUS_SLIDE", 0x21: "PREVIOUS_SLIDE", 0x50: "PREVIOUS_SLIDE",
    0x1B: "END_PRESENTATION",
}
MEDIA_KEYS = {0xB0: "NEXT_TRACK", 0xB1: "PREVIOUS_TRACK", 0xB3: "TOGGLE_PLAYBACK"}
CONTROL_KEYS = PRESENTATION_KEYS.keys() | MEDIA_KEYS.keys()


@dataclass(frozen=True)
class ObservedAction:
    action_type: str
    target: str
    activity: str
    active_app: str
    observed_at: float


class ControlKeyFilter:
    """Discard text, injected events, modifier chords and held-key repeats."""

    def __init__(self):
        self._held: set[int] = set()

    def handle(self, vk: int, *, key_down: bool, injected: bool, modifiers: bool,
               active_app: str | None, observed_at: float,
               presentation_mode: bool = False) -> ObservedAction | None:
        if vk not in CONTROL_KEYS or injected:
            return None
        if not key_down:
            self._held.discard(vk)
            return None
        if vk in self._held:
            return None
        self._held.add(vk)
        if modifiers or not active_app:
            return None
        try:
            activity, active_app = resolve_context(None, active_app)
        except ValueError:
            return None
        app = active_app.casefold()
        # In an editor, N/Space/arrows may edit text or move an object. Observe
        # them only in the PowerPoint slide-show window, never the editor.
        slide_show = presentation_mode or (
            "powerpoint" in app and ("slide show" in app or "슬라이드 쇼" in app)
        )
        if activity == "presentation" and slide_show:
            action, target = PRESENTATION_KEYS.get(vk), "powerpoint"
        elif activity == "music":
            action, target = MEDIA_KEYS.get(vk), "media_player"
        else:
            return None
        if action is None:
            return None
        return ObservedAction(action, target, activity, active_app, observed_at)


class WindowsHookAdapter:
    """Minimal native adapter, isolated so tests never install a real hook."""

    def __init__(self):
        self.thread_id: int | None = None

    def run(self, emit: Callable[[ObservedAction], None], ready: threading.Event):
        from ctypes import wintypes

        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

        class KeyboardData(ctypes.Structure):
            _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                        ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                        ("dwExtraInfo", ctypes.c_size_t)]

        user32.SetWindowsHookExW.argtypes = [ctypes.c_int, callback_type, wintypes.HINSTANCE, wintypes.DWORD]
        user32.SetWindowsHookExW.restype = wintypes.HANDLE
        user32.CallNextHookEx.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        user32.CallNextHookEx.restype = ctypes.c_ssize_t
        user32.UnhookWindowsHookEx.argtypes = [wintypes.HANDLE]
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        key_filter = ControlKeyFilter()

        @callback_type
        def callback(code, message, data_pointer):
            try:
                if code >= 0 and message in (0x100, 0x101, 0x104, 0x105):
                    data = ctypes.cast(data_pointer, ctypes.POINTER(KeyboardData)).contents
                    if data.vkCode in CONTROL_KEYS and not data.flags & 0x12:
                        # Capture app and monotonic time at the event, before the
                        # target app can change focus or finish a slide show.
                        observed_at = time.monotonic()
                        window = user32.GetForegroundWindow()
                        title, class_name = ctypes.create_unicode_buffer(512), ctypes.create_unicode_buffer(128)
                        user32.GetWindowTextW(window, title, len(title))
                        user32.GetClassNameW(window, class_name, len(class_name))
                        app = title.value.strip()
                        presentation_mode = class_name.value.casefold() == "screenclass"
                        if presentation_mode and "powerpoint" not in app.casefold():
                            app = f"PowerPoint {app}"
                        modifiers = bool(data.flags & 0x20) or any(
                            user32.GetAsyncKeyState(key) & 0x8000 for key in (0x10, 0x11, 0x12, 0x5B, 0x5C)
                        )
                        action = key_filter.handle(
                            data.vkCode, key_down=message in (0x100, 0x104), injected=False,
                            modifiers=modifiers, active_app=app, observed_at=observed_at,
                            presentation_mode=presentation_mode,
                        )
                        if action is not None:
                            emit(action)
            except Exception:
                # A callback failure must never suppress or alter user input.
                pass
            return user32.CallNextHookEx(None, code, message, data_pointer)

        self.thread_id = kernel32.GetCurrentThreadId()
        message = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 0)
        hook = user32.SetWindowsHookExW(13, callback, kernel32.GetModuleHandleW(None), 0)
        if not hook:
            raise OSError("Could not install Windows application-control observer")
        ready.set()
        try:
            while True:
                result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result == -1:
                    raise OSError("Windows observer message loop failed")
                if result == 0:
                    break
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
        finally:
            user32.UnhookWindowsHookEx(hook)

    def stop(self):
        if self.thread_id is not None:
            ctypes.windll.user32.PostThreadMessageW(self.thread_id, 0x12, 0, 0)


class WindowsInputObserver:
    def __init__(self, adapter=None):
        self.adapter = adapter or WindowsHookAdapter()
        self._events: queue.Queue[ObservedAction] = queue.Queue(maxsize=128)
        self._ready = threading.Event()
        self._error: Exception | None = None
        self._thread: threading.Thread | None = None

    def _emit(self, event: ObservedAction):
        try:
            self._events.put_nowait(event)
        except queue.Full:
            # Delayed input must not become a future training label.
            pass

    def _run(self):
        try:
            self.adapter.run(self._emit, self._ready)
        except Exception as error:
            self._error = error
        finally:
            self._ready.set()

    def start(self):
        # The Windows gate only guards the native hook; an injected adapter
        # (tests, or a future platform) brings its own capture mechanism.
        if isinstance(self.adapter, WindowsHookAdapter) and platform.system() != "Windows":
            raise OSError("Native input observation requires Windows; use --input-mode labels for simulation")
        self._thread = threading.Thread(target=self._run, name="application-control-observer", daemon=True)
        self._thread.start()
        if not self._ready.wait(2):
            self.stop()
            raise OSError("Windows input observer did not start")
        if self._error:
            raise OSError("Windows input observer failed to start") from self._error

    def drain(self) -> list[ObservedAction]:
        if self._error:
            raise OSError("Windows input observer stopped") from self._error
        events = []
        while True:
            try:
                events.append(self._events.get_nowait())
            except queue.Empty:
                return events

    def stop(self):
        self.adapter.stop()
        if self._thread:
            self._thread.join(timeout=2)
