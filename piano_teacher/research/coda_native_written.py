"""Bare native Coda notation for independent author differential checks.

Intentionally excludes source expression annotations: the output only
certifies pitch, rhythm, rests and written ties for one selected voice.
Full source-annotation projection has a separate acceptance gate.
"""
from __future__ import annotations

from dataclasses import replace

from ..notation.lesson import build_lesson_score
from .coda_differential import written_from_musicxml
from .coda_score_projection import _original_metadata


def render_native_written(plan, owners, piece, bars, *, factor):
    """Build and parse actual native MusicXML for one source-owned voice."""
    source = plan.original.phrase
    if source.start != 0 or source.first_bar != 1:
        raise ValueError("Comparison needs a bar-one source excerpt")
    end = piece.bar_boundaries[bars]
    excerpt = replace(
        piece, bar_boundaries=tuple(piece.bar_boundaries[:bars+1]),
        time_signatures=tuple(t for t in piece.time_signatures if t[0]<end),
        key_signatures=tuple(v for v in piece.key_signatures if v.beat<end),
        clef_changes=tuple(v for v in piece.clef_changes if v.beat<end))
    grid, meters, keys, clefs = _original_metadata(
        excerpt, source, plan, factor)
    selected = replace(
        plan.exercise_phrase, first_bar=1, last_bar=len(grid)-1,
        notes=tuple(note for i, note in enumerate(plan.exercise_phrase.notes)
                    if i in owners))
    if not selected.notes:
        raise ValueError("No owned source-voice notes to render")
    native = build_lesson_score(
        selected,boundaries=grid,time_signatures=meters,
        key_signatures=keys,clef_changes=clefs,retimed_source=True)
    return written_from_musicxml(native.musicxml)
