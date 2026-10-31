"""Choose initial lesson BPM from persistent fast MIDI attack intervals.

MIDI key-release length can reflect articulation or sustain, not the written
rhythmic value. Ignore isolated rolled-chord/grace timing.
"""
from __future__ import annotations

from .music import Phrase


def suggested_start_bpm(phrase: Phrase, hand: str, *,
                        default_bpm: int, minimum_bpm: int) -> int:
    """Aim for 0.5 s between repeated fast attacks (16ths -> 30 BPM)."""
    onsets = sorted({round(n.start, 6) for n in phrase.notes
                     if hand == "both" or n.hand == hand})
    rapid = sorted(b-a for a, b in zip(onsets, onsets[1:])
                   if 0.12 <= b-a < 0.5-1e-6)
    if len(rapid) < 2:
        return default_bpm
    gap_beats = rapid[max(1, len(rapid)//4)]
    pace_bpm = round(60.0 * gap_beats / 0.5)
    return min(default_bpm, max(minimum_bpm, pace_bpm))
