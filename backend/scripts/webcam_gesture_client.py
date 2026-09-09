import argparse
import time
import math
import sys
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


def action_for_key(key: int, activity: str) -> tuple[str, str] | None:
    return KEY_ACTIONS.get((chr(key), activity))


def horizontal_motion(flow, foreground_mask, threshold=1.0, min_motion_ratio=0.01):
    """Aggregate only moving foreground pixels; never retain image data."""
    import numpy as np

    dx, dy = flow[..., 0], flow[..., 1]
    mask = (np.abs(dx) > threshold) & foreground_mask & np.isfinite(dx) & np.isfinite(dy)
    ratio = float(np.mean(mask))
    if ratio <= min_motion_ratio:
        return None, ratio
    mean_dx, mean_dy = float(np.mean(dx[mask])), float(np.mean(dy[mask]))
    if abs(mean_dx) <= 0.3 or abs(mean_dx) <= abs(mean_dy):
        return None, ratio
    return ("right" if mean_dx > 0 else "left"), ratio


def observation_payload(user_id: str, activity: str, active_app: str, direction: str):
    if direction not in {"left", "right"}:
        raise ValueError("Only horizontal swipes are supported")
    return {
        "user_id": user_id,
        "context": {"active_app": active_app, "activity": activity,
                    "space": "camera_demo", "device": "laptop"},
        "gesture": {"motion_type": "swipe", "direction": direction, "duration_ms": 430},
        "attempt_inference": True,
    }


def main() -> int:

    parser = argparse.ArgumentParser(description="Local optical-flow gesture client")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--user-id", default="demo-user")
    parser.add_argument("--activity", choices=["presentation", "music"], default="presentation")
    parser.add_argument("--active-app", default=None)
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
    simulation_url = args.api_url.split("/api/")[0]
    print(f"Stable Simulation: open {simulation_url} in your browser. Q exits the camera.")
    try:
        import cv2
        import numpy as np
    except ImportError:
        print('Camera dependencies missing. Install: python -m pip install -e ".[camera]"', file=sys.stderr)
        return 1

    active_app = args.active_app or ("PowerPoint" if args.activity == "presentation" else "Spotify")
    teaching_keys = "N/B/Space" if args.activity == "music" else "N/B"
    key_help = "Q quit | N next | B previous"
    if args.activity == "music":
        key_help += " | Space play/pause"
    capture = cv2.VideoCapture(args.camera)
    if not capture.isOpened():
        capture.release()
        print("Camera could not be opened: check device index and camera permissions. Use Stable Simulation above.", file=sys.stderr)
        return 1

    previous_gray = None
    background_model = cv2.createBackgroundSubtractorMOG2(
        history=120, varThreshold=25, detectShadows=False
    )
    direction_history: list[str] = []
    last_detection = 0.0
    detection_count = 0
    latest_observation_id: str | None = None
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
                direction, moving_ratio = horizontal_motion(
                    flow, foreground_mask, args.threshold, args.min_motion_ratio
                )
                now = time.monotonic()
                if direction and now - last_detection >= 1.2:
                    direction_history.append(direction)
                    direction_history = direction_history[-args.stable_frames:]
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
                    print(
                        f"DETECTED: {direction} "
                        f"(max|dx|={max_abs_dx:.2f}, moving_ratio={moving_ratio:.1%}) "
                        f"#{detection_count}"
                    )
                    payload = observation_payload(
                        args.user_id, args.activity, active_app, direction
                    )
                    result = post_json(f"{args.api_url}/observe", payload)
                    latest_observation_id = result["observation"]["id"]
                    inference = result["inference"]
                    if inference["matched"]:
                        overlay = f"{direction} -> {inference['intent']} ({inference['confidence']:.0%})"
                    else:
                        overlay = f"Observed {direction}. Press {teaching_keys} to teach the next action."
                    print(overlay)
                    last_detection = now

            previous_gray = gray
            cv2.rectangle(frame, (x1, y1), (x2, y2), (104, 224, 255), 2)
            cv2.putText(frame, overlay[:85], (24, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (255, 255, 255), 2)
            cv2.putText(frame, f"detections: {detection_count}", (24, 66), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (104, 224, 255), 2)
            cv2.putText(frame, key_help, (24, height - 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 220, 220), 1)
            cv2.imshow("SilentOrchestra 2.0 - Local Optical Flow", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            teaching = action_for_key(key, args.activity)
            if teaching and latest_observation_id:
                intent, target = teaching
                result = post_json(
                    f"{args.api_url}/teach",
                    {
                        "user_id": args.user_id,
                        "observation_id": latest_observation_id,
                        "action_type": intent,
                        "target": target,
                        "parameters": {},
                    },
                )
                overlay = f"Learning {intent}: {result['progress_current']}/{result['progress_required']}"
                if result.get("suggestion"):
                    overlay += " - suggestion ready in web UI"
                print(overlay)
                latest_observation_id = None
    except (requests.RequestException, ValueError, KeyError, TypeError) as error:
        print(f"API request/response failed ({type(error).__name__}). No frames saved. Use Stable Simulation above; check the API server.", file=sys.stderr)
        return 1
    except cv2.error:
        print("Camera processing/display failed. Check camera permissions and display support. Use Stable Simulation above.", file=sys.stderr)
        return 1
    finally:
        capture.release()
        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
