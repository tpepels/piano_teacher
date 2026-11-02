"""MIDI-first research grid: exact source ticks instead of Coda's XML grid.

The original author's shortest-*written*-note quantizer is retained only for
upstream reproduction. MIDI exercises derive ticks from the actual SMF PPQ;
no altered attack/release times, inferred rests, or invented authored voices.
"""
from __future__ import annotations

from math import gcd, isfinite

from ..music import Piece, Phrase

MAX_MATRIX_CELLS = 2_000_000


def midi_coda_quantization(
    piece: Piece, phrase: Phrase, *, dotted: bool = False,
    compact: bool = False, max_cells: int | None = MAX_MATRIX_CELLS,
) -> int:
    """Choose PPQ-exact source grid; double it for half-tick dotted rhythms.

    Return an integer ticks-per-quarter grid, or reject costly/ambiguous inputs
    without rounding. The cap is the current 128-pitch matrix allocation limit.
    """
    ppq = piece.midi_ticks_per_beat
    if piece.source_format != "midi" or piece.source_musicxml or ppq <= 0:
        raise ValueError("Coda MIDI grid requires a genuine MIDI-imported Piece")
    if not phrase.notes or phrase.start < 0 or phrase.end <= phrase.start:
        raise ValueError("Coda MIDI grid requires a nonempty bounded phrase")
    if max_cells is not None and max_cells <= 0:
        raise ValueError("Coda MIDI matrix needs a positive capacity")
    g = ppq
    for note in phrase.notes:
        if note.start < phrase.start-1e-8 or note.end > phrase.end+1e-8:
            raise ValueError("Coda MIDI phrase crosses its selected boundaries")
        for beat in (note.start, note.end):
            ticks = beat*ppq
            if not isfinite(ticks) or abs(ticks-round(ticks))>1e-5:
                raise ValueError("Coda MIDI input event is not aligned to original PPQ")
            if compact:
                g = gcd(g, abs(round(ticks)))
    if compact:
        # Include all passage bar boundaries: selecting a coarser grid
        # must still represent every original meter transition exactly.
        for boundary in piece.bar_boundaries:
            if phrase.start-1e-7 <= boundary <= phrase.end+1e-7:
                ticks=boundary*ppq
                if not isfinite(ticks) or abs(ticks-round(ticks))>1e-5:
                    raise ValueError("Coda MIDI barline is not aligned to original PPQ")
                g=gcd(g,abs(round(ticks)))
    q = (ppq//g if compact else ppq) * (2 if dotted else 1)
    steps = (phrase.end-phrase.start)*q
    if not isfinite(steps) or (max_cells is not None and steps*128 > max_cells):
        raise ValueError("Coda MIDI source exceeds bounded matrix capacity")
    return q
