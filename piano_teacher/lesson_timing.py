"""Count-in duration at the exercise tempo, not a fixed number of bars."""
from __future__ import annotations
from math import floor


def preparation_meter(meter: tuple[int, int] | None,
                      time_signatures: tuple[tuple[float, int, int], ...],
                      at_beat: float) -> tuple[int, int] | None:
    """Use the next normal meter for an unusually short opening pickup.

    Imported scores such as Chopin Nocturne Op. 9 No. 2 encode a 1/8
    pickup followed half a beat later by 12/8. A half-beat count-in at
    practice speed gives the player almost no warning. Preserve the source
    meter for the score, but prepare using that immediately following full
    measure. Never scan arbitrarily far into the piece.
    """
    if meter is None or meter[0] * 4 / meter[1] >= 1.0:
        return meter
    for beat, num, den in sorted(time_signatures):
        if at_beat + 1e-7 < beat <= at_beat + 1.0 + 1e-7 and num * 4 / den >= 1.0:
            return num, den
    return meter


def lead_in_beats(bar_beats: float, bpm: float, max_seconds: float = 4.0) -> float:
    """Up to one bar, capped to about four seconds at slow practice tempos.

    Use half-quarter-note steps when a full beat would create a long wait.
    The transport still moves continuously at the chosen BPM.
    """
    if bar_beats <= 0 or bpm <= 0 or max_seconds <= 0:
        raise ValueError("Count-in requires positive meter, BPM and duration")
    available = floor(max_seconds * bpm / 60.0 * 2.0 + 1e-9) / 2.0
    return min(bar_beats, max(.5, available))
