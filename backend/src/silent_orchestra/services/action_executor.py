import ctypes
import platform
import subprocess

from ..config import settings


KEY_MAP = {
    "NEXT_SLIDE": "right",
    "PREVIOUS_SLIDE": "left",
    "START_PRESENTATION": "f5",
    "END_PRESENTATION": "esc",
    "NEXT_TRACK": "nexttrack",
    "PREVIOUS_TRACK": "prevtrack",
    "TOGGLE_PLAYBACK": "playpause",
    "VOLUME_UP": "volumeup",
    "VOLUME_DOWN": "volumedown",
    "ZOOM_IN": "+",
    "ZOOM_OUT": "-",
}

# ponytail: calibration knob. Matched case-insensitively as substrings against
# the frontmost window, because real machines name it differently per app and
# per OS ("Microsoft PowerPoint" on macOS, "... - PowerPoint" on Windows).
# Add the app you actually present with rather than loosening the check.
TARGET_WINDOWS = {
    "powerpoint": ("powerpoint", "keynote", "slides", "impress"),
    "media_player": ("spotify", "music", "itunes", "vlc"),
}

_FRONTMOST_APP = (
    'tell application "System Events" to get name of first process whose frontmost is true'
)
# ponytail: the process name alone is "Google Chrome", so title-based entries
# ("slides", "impress") never match on macOS. The title needs Accessibility
# permission, so we ask for it separately and keep the name when it is denied.
_FRONTMOST_TITLE = (
    'tell application "System Events" to tell (first process whose frontmost is true) '
    "to get name of front window"
)


def _osascript(script: str) -> str | None:
    result = subprocess.run(
        ["osascript", "-e", script], capture_output=True, text=True, timeout=2, check=True
    )
    return result.stdout.strip() or None


def active_window() -> str | None:
    """Frontmost window/app name, or None when this platform or its permissions cannot report it."""
    system = platform.system()
    try:
        if system == "Darwin":
            name = _osascript(_FRONTMOST_APP)
            try:
                title = _osascript(_FRONTMOST_TITLE)
            except Exception:  # pragma: no cover - Accessibility permission denied
                title = None
            return " ".join(part for part in (name, title) if part) or None
        if system == "Windows":
            user32 = ctypes.windll.user32  # type: ignore[attr-defined]
            buffer = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(user32.GetForegroundWindow(), buffer, 512)
            return buffer.value.strip() or None
    except Exception:  # pragma: no cover - OS/permission dependent
        return None
    return None  # ponytail: X11/Wayland needs an extra tool; run with SO_REQUIRE_ACTIVE_WINDOW=false


def check_active_window(target: str) -> str | None:
    """Return why the target app may not receive the key, or None when it is safe to send."""
    window = active_window()
    if window is None:
        return (
            "활성 창을 확인할 수 없어 실행하지 않았습니다. "
            "접근성 권한을 허용하거나 SO_REQUIRE_ACTIVE_WINDOW=false로 검증을 끄세요."
        )
    expected = TARGET_WINDOWS.get(target, (target,))
    if not any(name in window.lower() for name in expected):
        return f"대상 앱이 활성 상태가 아니어서 실행하지 않았습니다. 현재 활성 창: {window}"
    return None


def execute_action(intent: str, target: str) -> tuple[str, str, str | None]:
    if not settings.enable_os_actions:
        return "DRY_RUN", "SIMULATED", None

    key = KEY_MAP.get(intent)
    if key is None:
        return "OS", "FAILED", f"No operating-system key mapping for intent: {intent}"

    if settings.require_active_window:
        blocked = check_active_window(target)
        if blocked is not None:
            return "OS", "FAILED", blocked

    try:
        import pyautogui  # type: ignore[import-not-found]

        pyautogui.press(key)
        return "OS", "SUCCEEDED", None
    except Exception as exc:  # pragma: no cover - hardware/OS dependent
        return "OS", "FAILED", str(exc)
