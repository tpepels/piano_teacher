"""Count-in duration at the exercise tempo, not a fixed number of bars."""
from __future__ import annotations
from math import floor


def lead_in_beats(bar_beats: float, bpm: float, max_seconds: float = 4.0) -> float:
    """Up to one bar, capped to about four seconds at slow practice tempos.

    Use half-quarter-note steps when a full beat would create a long wait.
    The transport still moves continuously at the chosen BPM.
    """
    if bar_beats <= 0 or bpm <= 0 or max_seconds <= 0:
        raise ValueError("Count-in requires positive meter, BPM and duration")
    available = floor(max_seconds * bpm / 60.0 * 2.0 + 1e-9) / 2.0
    return min(bar_beats, max(.5, available))
