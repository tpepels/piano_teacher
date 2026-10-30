"""Single source of expected note timings for all grading modes.

The clock only supplies beat/second conversion. It has no score, MIDI
recording, renderer, history or transport side effects.
"""
from __future__ import annotations

from typing import Protocol

from .music import Note, Phrase


class BeatClock(Protocol):
    def seconds_at(self, beat: float) -> float: ...
    def bpm_at(self, beat: float) -> float: ...


def expected_note_seconds(phrase: Phrase, clock: BeatClock, from_beat: float = 0.0):
    """Return attack, release and local seconds/beat for each source note.

    Recorder times use the current attempt's origin, including partial retries.
    """
    origin = clock.seconds_at(from_beat)

    def expected(note: Note) -> tuple[float, float, float]:
        attack = note.start - phrase.start
        release = min(note.end, phrase.end) - phrase.start
        return (clock.seconds_at(attack) - origin,
                clock.seconds_at(release) - origin,
                60.0 / clock.bpm_at(attack))

    return expected
