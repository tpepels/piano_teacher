"""Incremental student feedback for the most recent two-bar practice window.

Only settled notes are scored. Waiting for the expected release and an onset
grace period avoids false "missed" or "short" flashes while a key is held.
No video-frame clock or Godot interaction is involved.
"""
from __future__ import annotations
from .music import Phrase
from .practice import Assessment, PlayedNote, evaluate


def settled_assessment(phrase: Phrase, hand: str, bpm: float,
                       played: list[PlayedNote], *, from_beat: float,
                       until_beat: float, beats_per_bar: float) -> Assessment | None:
    if bpm <= 0 or beats_per_bar <= 0:
        raise ValueError("Tempo and measure length must be positive")
    grace = .12 * bpm / 60  # 120 ms after expected note release
    earliest = max(from_beat, until_beat - 2*beats_per_bar)
    required = tuple(
        n for n in phrase.notes
        if (hand == "both" or n.hand == hand)
        and phrase.start+earliest-1e-7 <= n.start
        and n.end <= phrase.start+until_beat-grace+1e-7
    )
    if not required:
        return None
    # PlayedNote timestamps have the same origin as the whole current take.
    # Keeping that origin avoids drift at restarts and recovery sub-passages.
    passage = Phrase(phrase.number, phrase.first_bar, phrase.last_bar,
                     phrase.start+from_beat, phrase.end, required)
    # Do not classify notes that occur later in the take as "extras" yet.
    # This also makes deterministic prerecorded performance fixtures valid.
    upto = (until_beat-from_beat)*60/bpm+.12
    since = max(0.0,(earliest-from_beat)*60/bpm-.15)
    eligible = [n for n in played if since <= n.onset <= upto]
    result = evaluate(passage, hand, bpm, eligible)
    # Project only required settled notes here. Early/key mistakes remain
    # marked at their corresponding noteheads; extra-note labels are shown
    # in the final assessment to avoid a misleading moving marker.
    return Assessment(result.notes, 0, ())
