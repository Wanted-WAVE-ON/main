import argparse
import math
import platform
import sys
import time
from typing import Any

import requests


def post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(url, json=payload, timeout=5)
    response.raise_for_status()
    return response.json()


KEY_ACTIONS = {
    ("n", "presentation"): ("NEXT_SLIDE", "powerpoint"),
    ("n", "music"): ("NEXT_TRACK", "media_player"),
    ("b", "presentation"): ("PREVIOUS_SLIDE", "powerpoint"),
    ("b", "music"): ("PREVIOUS_TRACK", "media_player"),
    (" ", "music"): ("TOGGLE_PLAYBACK", "media_player"),
}

TEACH_WINDOW_SECONDS = 5.0


def action_for_key(key: int, activity: str) -> tuple[str, str] | None:
    return KEY_ACTIONS.get((chr(key), activity))


def make_input_observer():
    """Isolated so tests inject a fake and never install a real keyboard hook."""
    from silent_orchestra.services.input_observer import WindowsInputObserver

    return WindowsInputObserver()


def horizontal_motion(flow, foreground_mask, threshold=1.0, min_motion_ratio=0.01):
    """Aggregate only moving foreground pixels; never retain image data.

    Returns ``(direction, moving_ratio, mean_dx)`` so the caller can accumulate
    the swipe amplitude without touching pixel data a second time.
    """
    import numpy as np

    dx, dy = flow[..., 0], flow[..., 1]
    mask = (np.abs(dx) > threshold) & foreground_mask & np.isfinite(dx) & np.isfinite(dy)
    ratio = float(np.mean(mask))
    if ratio <= min_motion_ratio:
        return None, ratio, 0.0
    mean_dx, mean_dy = float(np.mean(dx[mask])), float(np.mean(dy[mask]))
    if abs(mean_dx) <= 0.3 or abs(mean_dx) <= abs(mean_dy):
        return None, ratio, mean_dx
    return ("right" if mean_dx > 0 else "left"), ratio, mean_dx


def measured_features(dx_pixels: float, duration_seconds: float, roi_width: int) -> tuple[float, float]:
    """ROI-relative amplitude (widths) and speed (widths/second), clamped to the API range."""
    span = max(roi_width, 1)
    amplitude = min(abs(dx_pixels) / span, 10.0)
    speed = min(amplitude / duration_seconds, 10.0) if duration_seconds > 0 else 0.0
    return round(speed, 4), round(amplitude, 4)


def select_observed_teach(events, pending):
    """First real key in the same activity inside the window; None once it expires.

    ``events`` arrive in observation order, so a first event past the window means
    every later one is too. Only the first match is linked (SPEC L-9).
    """
    _, obs_activity, obs_ts = pending
    for event in events:
        if event.observed_at - obs_ts > TEACH_WINDOW_SECONDS:
            return None
        if event.activity == obs_activity:
            return event
    return None


def observation_payload(user_id, activity, active_app, direction, *,
                        duration_ms=430, speed=None, amplitude=None, attempt_inference=True):
    if direction not in {"left", "right"}:
        raise ValueError("Only horizontal swipes are supported")
    if (speed is None) != (amplitude is None):
        raise ValueError("speed and amplitude must be provided together")
    context: dict[str, Any] = {"space": "camera_demo", "device": "laptop"}
    if activity is not None:
        context["activity"] = activity
    if active_app is not None:
        context["active_app"] = active_app
    gesture: dict[str, Any] = {
        "motion_type": "swipe", "direction": direction, "duration_ms": duration_ms,
    }
    if speed is not None:
        gesture["speed"] = speed
        gesture["amplitude"] = amplitude
    return {
        "user_id": user_id,
        "context": context,
        "gesture": gesture,
        "attempt_inference": attempt_inference,
    }


def _teach(api_url, user_id, observation_id, action_type, target) -> str:
    result = post_json(
        f"{api_url}/teach",
        {"user_id": user_id, "observation_id": observation_id,
         "action_type": action_type, "target": target, "parameters": {}},
    )
    overlay = f"Learning {action_type}: {result['progress_current']}/{result['progress_required']}"
    if result.get("suggestion"):
        overlay += " - suggestion ready in web UI"
    return overlay


def main() -> int:

    parser = argparse.ArgumentParser(description="Local optical-flow gesture client")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--user-id", default="demo-user")
    parser.add_argument("--input-mode", choices=["observe", "labels"], default="observe",
                        help="observe real app keys (Windows) or label the next action by hand")
    parser.add_argument("--activity", choices=["auto", "presentation", "music"], default="auto",
                        help="auto resolves the activity from the active app; a value is a manual override")
    parser.add_argument("--learn", action="store_true",
                        help="disable inference so approved memories do not auto-execute while (re)learning")
    parser.add_argument("--active-app", default=None,
                        help="labels mode only: metadata override for the recorded app name")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--threshold", type=float, default=1.0,
                        help="per-pixel horizontal flow magnitude that counts as motion")
    parser.add_argument("--min-motion-ratio", type=float, default=0.01,
                        help="fraction of ROI pixels in motion required to trigger a detection")
    parser.add_argument("--stable-frames", type=int, default=3,
                        help="consecutive frames that must agree on direction")
    args = parser.parse_args()

    if not math.isfinite(args.threshold) or args.threshold <= 0:
        parser.error("--threshold must be finite and greater than zero")
    if not 0 < args.min_motion_ratio <= 1:
        parser.error("--min-motion-ratio must be in (0, 1]")
    if args.stable_frames < 1:
        parser.error("--stable-frames must be at least 1")
    if args.input_mode == "labels" and args.activity == "auto":
        parser.error("--input-mode labels needs an explicit --activity (presentation or music)")
    if args.input_mode == "observe" and platform.system() != "Windows":
        parser.error("--input-mode observe needs Windows; use --input-mode labels on this platform")
    if args.input_mode == "observe" and args.active_app:
        parser.error("--input-mode observe reads the real active window; --active-app is labels only")

    simulation_url = args.api_url.split("/api/")[0]
    print(f"Stable Simulation: open {simulation_url} in your browser. Q exits the camera.")
    try:
        import cv2
        import numpy as np
    except ImportError:
        print('Camera dependencies missing. Install: python -m pip install -e ".[camera]"', file=sys.stderr)
        return 1

    request_activity = None if args.activity == "auto" else args.activity
    if args.input_mode == "labels":
        # Labels mode never reads the OS; the recorded app name is metadata only.
        active_app = args.active_app or ("PowerPoint" if args.activity == "presentation" else "Spotify")
        key_help = "Q quit | N next | B previous"
        if args.activity == "music":
            key_help += " | Space play/pause"
    else:
        # Observe mode: the server reads its own active window, and the real keys
        # you press in the app are what get linked. No spoofing here.
        active_app = None
        key_help = "Q quit | use your usual keys in the app"

    capture = cv2.VideoCapture(args.camera)
    if not capture.isOpened():
        capture.release()
        print("Camera could not be opened: check device index and camera permissions. Use Stable Simulation above.", file=sys.stderr)
        return 1

    observer = None
    if args.input_mode == "observe":
        try:
            observer = make_input_observer()
            observer.start()
        except OSError as error:
            capture.release()
            print(f"Real input observation could not start ({error}). Use --input-mode labels. Stable Simulation above.", file=sys.stderr)
            return 1

    previous_gray = None
    background_model = cv2.createBackgroundSubtractorMOG2(
        history=120, varThreshold=25, detectShadows=False
    )
    direction_history: list[str] = []
    last_detection = 0.0
    detection_count = 0
    pending_teach: tuple[str, str, float] | None = None
    segment_start = 0.0
    segment_dx = 0.0
    overlay = "Move one hand horizontally inside the guide"

    try:
        post_json(f"{args.api_url}/demo/bootstrap", {})
        while True:
            ok, frame = capture.read()
            if not ok:
                print("Camera frame read failed. Use Stable Simulation above.", file=sys.stderr)
                return 1
            frame = cv2.flip(frame, 1)
            height, width = frame.shape[:2]
            x1, y1 = int(width * 0.18), int(height * 0.20)
            x2, y2 = int(width * 0.82), int(height * 0.82)
            roi_width = x2 - x1
            roi = frame[y1:y2, x1:x2]
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (7, 7), 0)

            if previous_gray is not None:
                flow = cv2.calcOpticalFlowFarneback(
                    previous_gray, gray, None, 0.5, 3, 21, 3, 5, 1.2, 0
                )
                # A moving hand only occupies a fraction of the ROI, so a median
                # over every pixel washes out to ~0. Look at the pixels that are
                # actually in motion instead.
                dx = flow[..., 0]
                dy = flow[..., 1]
                foreground_mask = background_model.apply(gray) > 0
                direction, moving_ratio, mean_dx = horizontal_motion(
                    flow, foreground_mask, args.threshold, args.min_motion_ratio
                )
                now = time.monotonic()
                if direction and now - last_detection >= 1.2:
                    if not direction_history:
                        # Start of a swipe segment: time it and its amplitude.
                        segment_start = now
                        segment_dx = 0.0
                    direction_history.append(direction)
                    direction_history = direction_history[-args.stable_frames:]
                    segment_dx += abs(mean_dx)
                else:
                    direction_history.clear()
                if (
                    len(direction_history) == args.stable_frames
                    and len(set(direction_history)) == 1
                ):
                    max_abs_dx = float(np.max(np.abs(dx)))
                    direction = direction_history[-1]
                    direction_history.clear()
                    detection_count += 1
                    duration_s = max(now - segment_start, 1e-3)
                    duration_ms = int(min(duration_s, 10.0) * 1000)
                    speed, amplitude = measured_features(segment_dx, duration_s, roi_width)
                    print(
                        f"DETECTED: {direction} "
                        f"(max|dx|={max_abs_dx:.2f}, moving_ratio={moving_ratio:.1%}, "
                        f"speed={speed:.2f}w/s, amp={amplitude:.2f}w) #{detection_count}"
                    )
                    payload = observation_payload(
                        args.user_id, request_activity, active_app, direction,
                        duration_ms=duration_ms, speed=speed, amplitude=amplitude,
                        attempt_inference=not args.learn,
                    )
                    result = post_json(f"{args.api_url}/observe", payload)
                    observation_id = result["observation"]["id"]
                    resolved_activity = result["context"]["activity"]
                    inference = result["inference"]
                    if inference["matched"]:
                        overlay = f"{direction} -> {inference['intent']} ({inference['confidence']:.0%})"
                        pending_teach = None
                    elif args.input_mode == "observe":
                        overlay = (
                            f"Observed {direction} in {resolved_activity}. "
                            f"Use your usual key in the app within {int(TEACH_WINDOW_SECONDS)}s."
                        )
                        pending_teach = (observation_id, resolved_activity, now)
                    else:
                        teach_keys = "N/B/Space" if resolved_activity == "music" else "N/B"
                        overlay = f"Observed {direction}. Press {teach_keys} to teach the next action."
                        pending_teach = (observation_id, resolved_activity, now)
                    print(overlay)
                    last_detection = now

            previous_gray = gray

            if observer is not None and pending_teach is not None:
                try:
                    events = observer.drain()
                except OSError as error:
                    print(f"Real input observer stopped ({error}). Use --input-mode labels. Stable Simulation above.", file=sys.stderr)
                    return 1
                chosen = select_observed_teach(events, pending_teach)
                if chosen is not None:
                    overlay = _teach(
                        args.api_url, args.user_id, pending_teach[0],
                        chosen.action_type, chosen.target,
                    )
                    print(overlay)
                    pending_teach = None
            if pending_teach is not None and time.monotonic() - pending_teach[2] > TEACH_WINDOW_SECONDS:
                pending_teach = None

            cv2.rectangle(frame, (x1, y1), (x2, y2), (104, 224, 255), 2)
            cv2.putText(frame, overlay[:85], (24, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (255, 255, 255), 2)
            cv2.putText(frame, f"detections: {detection_count}", (24, 66), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (104, 224, 255), 2)
            cv2.putText(frame, key_help, (24, height - 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 220, 220), 1)
            cv2.imshow("SilentOrchestra 2.0 - Local Optical Flow", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if args.input_mode == "labels" and pending_teach is not None:
                teaching = action_for_key(key, pending_teach[1])
                if teaching:
                    intent, target = teaching
                    overlay = _teach(args.api_url, args.user_id, pending_teach[0], intent, target)
                    print(overlay)
                    pending_teach = None
    except (requests.RequestException, ValueError, KeyError, TypeError) as error:
        print(f"API request/response failed ({type(error).__name__}). No frames saved. Use Stable Simulation above; check the API server.", file=sys.stderr)
        return 1
    except cv2.error:
        print("Camera processing/display failed. Check camera permissions and display support. Use Stable Simulation above.", file=sys.stderr)
        return 1
    finally:
        if observer is not None:
            observer.stop()
        capture.release()
        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
