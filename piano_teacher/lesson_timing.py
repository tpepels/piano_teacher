"""Count-in length: one full bar of the preparation meter."""
from __future__ import annotations


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


def lead_in_beats(bar_beats: float, bpm: float) -> float:
    """The count-in is always one full bar of the preparation meter.

    Owner decision 2026-11-08: "Ichi, Ni, San, Shi" over the whole bar at
    any tempo (6 s for 4/4 at 40 BPM). The former count_in_max_seconds
    cap, which shortened slow count-ins to half-beat steps, is removed.
    """
    if bar_beats <= 0 or bpm <= 0:
        raise ValueError("Count-in requires positive meter and BPM")
    return float(bar_beats)
