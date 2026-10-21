"""Strict source-measure equivalence for tempo transfer, never mastery credit.

A repeated passage must contain the same sounding notes, attacks, held
durations and source-measure pattern. Source IDs, staff glyphs and absolute
onsets identify *where* a performance happens; they must not prevent tempo
carry-over to a genuinely repeated occurrence. Transposed or rhythmically
altered material deliberately does not match.
"""
from __future__ import annotations

from .music import Phrase, Piece


def exact_repetition_signature(piece: Piece, phrase: Phrase, hand: str,
                               level: str, *, minimum_attacks: int) -> tuple | None:
    if len(phrase.notes) < minimum_attacks:
        return None

    def beats(value: float) -> int:
        # MIDI events are in quarter-note beats. Six decimal places are
        # substantially tighter than a timed-performance grading window.
        return round(value * 1_000_000)

    notes = tuple(sorted(
        (beats(note.start - phrase.start),
         beats(max(0.0, min(note.end, phrase.end) - note.start)),
         note.pitch, note.hand)
        for note in phrase.notes
    ))

    boundaries = piece.bar_boundaries
    if boundaries and 1 <= phrase.first_bar <= phrase.last_bar < len(boundaries):
        measures = tuple(
            beats(boundaries[i + 1] - boundaries[i])
            for i in range(phrase.first_bar - 1, phrase.last_bar)
        )
    else:
        # Hand-authored old fixtures may have no original grid. Such a
        # lesson still has a bounded musical duration.
        measures = (beats(phrase.end - phrase.start),)

    return hand, level, measures, notes
