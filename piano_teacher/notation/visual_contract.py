"""Image-free visual-ledger vocabulary, scalar checks and capture-name clocks."""
from __future__ import annotations

from math import isfinite


STATUSES = ("verified", "ambiguous", "unsupported", "unverified", "mismatch")
FLAG_COUNTS = {"eighth": 1, "16th": 2, "32nd": 3, "64th": 4, "128th": 5}


def source_number(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return value


def source_beat(value):
    return round(float(value), 8) if value is not None else None


def finite_score(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and isfinite(value) and 0 < value <= 1)


def valid_box(value):
    return (isinstance(value, (list, tuple)) and len(value) == 4
            and all(isinstance(x, (int, float)) and not isinstance(x, bool) and isfinite(x) for x in value)
            and value[0] < value[2] and value[1] < value[3])


def capture_frame_clock(frame):
    if (not isinstance(frame, str) or not frame.startswith("native-") or not frame.endswith(".png") or
            "/" in frame or "\\" in frame):
        return None
    try:
        clock = float(frame[7:-4])
    except ValueError:
        return None
    return clock if isfinite(clock) else None
