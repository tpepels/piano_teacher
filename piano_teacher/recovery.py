"""Two-measure, boundary-aligned failure detection for MIDI-led practice.

Work in original exercise beats so restarts and tempo changes do not cause
errors to drift. A wrong pitch replaces a miss rather than counting twice.
"""
from __future__ import annotations
from dataclasses import dataclass
from .music import Phrase
from .practice import PlayedNote, evaluate


@dataclass(frozen=True)
class RecoveryDecision:
    end_beat: float
    restart_beat: float
    errors: int
    wrong: int
    missed: int


def check_two_bar_window(phrase: Phrase, hand: str, bpm: int,
                         played: list[PlayedNote], *,
                         from_beat: float, end_beat: float,
                         beats_per_bar: float, threshold: int = 5,
                         window_start_beat: float | None = None) -> RecoveryDecision | None:
    """Return a rewind after five wrong/missed notes, or None.

    played timestamps begin at from_beat within the excerpt. The window
    is aligned to its ending two-bar boundary. evaluate() prevents
    counting one bad chord pitch as both wrong and missed.
    """
    if threshold <= 0 or beats_per_bar <= 0:
        raise ValueError("A positive error threshold and bar duration are required")
    end_beat = min(end_beat, phrase.end - phrase.start)
    # The source MIDI's bar grid is authoritative for changing meters.
    # The old fixed-length fallback remains for legacy synthetic fixtures.
    start_beat = max(from_beat, window_start_beat if window_start_beat is not None
                     else end_beat - 2 * beats_per_bar)
    if end_beat <= start_beat:
        return None
    selected = tuple(n for n in phrase.notes
                     if phrase.start + start_beat - 1e-7 <= n.start < phrase.start + end_beat - 1e-7
                     and (hand == "both" or n.hand == hand))
    if len(selected) < threshold:
        return None
    seconds = 60.0 / bpm
    window_seconds = (start_beat - from_beat) * seconds
    relative = [PlayedNote(n.pitch, n.onset - window_seconds,
                           n.release - window_seconds if n.release is not None else None)
                for n in played if window_seconds - .15 <= n.onset < (end_beat - from_beat) * seconds + .15]
    segment = Phrase(phrase.number, phrase.first_bar, phrase.last_bar,
                     phrase.start + start_beat, phrase.start + end_beat, selected)
    assessed = evaluate(segment, hand, bpm, relative)
    missed = sum(n.status == "missed" for n in assessed.notes)
    wrong = sum(n.status == "wrong" for n in assessed.notes)
    errors = missed + wrong
    return RecoveryDecision(end_beat, start_beat, errors, wrong, missed) if errors >= threshold else None
