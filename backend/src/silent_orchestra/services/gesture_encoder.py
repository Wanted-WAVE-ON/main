import math

DIRECTION_VECTORS: dict[str, tuple[float, float]] = {
    "right": (1.0, 0.0),
    "left": (-1.0, 0.0),
    "up": (0.0, 1.0),
    "down": (0.0, -1.0),
    "clockwise": (0.7, 0.7),
    "counterclockwise": (-0.7, 0.7),
    "none": (0.0, 0.0),
}

MOTION_CODES: dict[str, tuple[float, float, float]] = {
    "swipe": (1.0, 0.0, 0.0),
    "open_palm": (0.0, 1.0, 0.0),
    "pinch": (0.0, 0.0, 1.0),
    "circle": (0.7, 0.7, 0.0),
    "hold": (0.2, 0.4, 0.4),
}


def canonical(value: str) -> str:
    return value.strip().lower().replace(" ", "_").replace("-", "_")


def gesture_key(motion_type: str, direction: str) -> str:
    return f"{canonical(motion_type)}:{canonical(direction or 'none')}"


def encode_gesture(motion_type: str, direction: str, duration_ms: int) -> list[float]:
    motion = canonical(motion_type)
    direction_key = canonical(direction or "none")
    dx, dy = DIRECTION_VECTORS.get(direction_key, (0.0, 0.0))
    m1, m2, m3 = MOTION_CODES.get(motion, (0.33, 0.33, 0.33))
    duration = min(max(duration_ms / 1000.0, 0.0), 2.0) / 2.0
    vector = [dx, dy, m1, m2, m3, duration]
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [round(value / norm, 6) for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    lnorm = math.sqrt(sum(a * a for a in left))
    rnorm = math.sqrt(sum(b * b for b in right))
    if not lnorm or not rnorm:
        return 0.0
    return max(-1.0, min(1.0, dot / (lnorm * rnorm)))


def running_average(previous: list[float], current: list[float], previous_count: int) -> list[float]:
    if len(previous) != len(current) or previous_count <= 0:
        return current
    total = previous_count + 1
    return [
        round(((old * previous_count) + new) / total, 6)
        for old, new in zip(previous, current, strict=True)
    ]
