"""Canonical fixture preparation and immutable selected-source binding."""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path

from piano_teacher.application.score_preparation import assemble_layout
from piano_teacher.music import Phrase, source_note_id
from piano_teacher.notation.audit_annotations import CANONICAL_CAPTURE_CONFIG, canonical_piece
from piano_teacher.notation.lesson import build_lesson_score, infer_piece_clefs
from piano_teacher.notation.model import build_score_model
from piano_teacher.score import import_piece, render_layout

from .capture_store import ROOT
from .case_catalog import CASES
from .case_types import AuditCase

def variant_errors(source: Phrase, variant) -> list[str]:
    """A learning stage may select source attacks, never change or invent them."""
    indices = variant.source_indices
    if len(indices) != len(set(indices)):
        return ["Learning variant duplicates a source note"]
    if any(not isinstance(i, int) or not 0 <= i < len(source.notes) for i in indices):
        return ["Learning variant has an unknown source note index"]
    if tuple(source.notes[i] for i in indices) != variant.phrase.notes:
        return ["Learning variant changes or invents source pitch, timing or identity"]
    if (source.start, source.end, source.first_bar, source.last_bar) != (
            variant.phrase.start, variant.phrase.end,
            variant.phrase.first_bar, variant.phrase.last_bar):
        return ["Learning variant changes its source measure boundaries"]
    return []


def selected_source_errors(phrase: Phrase, model: dict) -> list[str]:
    """Bind the exact rendered payload to immutable selected source events."""
    expected = {}
    for i, note in enumerate(phrase.notes):
        expected[source_note_id(note, i)] = {
            "midi_pitch": note.pitch, "hand": note.hand,
            "track": note.track, "channel": note.channel, "velocity": note.velocity,
            "onset_beats": round(note.start-phrase.start, 8),
            "duration_beats": round(min(note.end, phrase.end)-note.start, 8)}
    errors = []
    actual = {note.get("id"): note for note in model.get("notes", [])}
    if len(actual) != len(model.get("notes", [])) or actual.keys() != expected.keys():
        errors.append("Captured payload has missing, duplicate or invented source-note identities")
    for ident, fields in expected.items():
        for field, value in fields.items():
            if actual.get(ident, {}).get(field) != value:
                errors.append(f"Source note {ident} {field}: expected {value}, "
                              f"observed {actual.get(ident, {}).get(field)}")
    active = {ident for ident, note in expected.items()
              if model.get("active_hand") in ("both", note["hand"])}
    if (set(model.get("active_note_ids", [])) != active or
            len(model.get("active_note_ids", [])) != len(active)):
        errors.append("Captured payload has an incorrect active-hand source-note set")
    return errors


def capture_clocks(xml: str) -> list[float]:
    from piano_teacher.notation.proof import read_written_score
    written = read_written_score(xml)
    clocks = {round(float(e["beat"]), 8) for e in written.symbols}
    clocks.update(round(float(beat), 8) for beat in written.bars)
    step = min(.0625, float(written.bars[-1])/4)
    clocks.update((0.0, round(step, 8), round(2*step, 8)))
    for boundary in written.bars[1:-1]:
        # Equal musical steps on either side expose a jump or freeze at a
        # measure join without prescribing the renderer's horizontal spacing.
        clocks.update((round(float(boundary)-step, 8),
                       round(float(boundary)+step, 8)))
    return sorted(clocks)


def fixture(case: AuditCase = CASES[0], *, piece=None,
            phrase: Phrase | None = None, cache=None) -> tuple[dict, object]:
    source = ROOT / (case.filename if "/" in case.filename
                     else "midi/" + case.filename)
    if piece is None:
        piece, _ = import_piece(source)
    # Normalize authored fingering before building either the lesson score or
    # its reference assets; the imported source and note identities stay intact.
    piece = canonical_piece(piece)
    assert 1 <= case.first_bar <= case.last_bar < len(piece.bar_boundaries)
    first = piece.bar_boundaries[case.first_bar - 1]
    end = piece.bar_boundaries[case.last_bar]
    notes = tuple(n for n in piece.notes if first <= n.start < end)
    original = phrase is None
    if phrase is None:
        phrase = Phrase(1, case.first_bar, case.last_bar, first, end, notes)
    score = build_lesson_score(
        phrase, boundaries=piece.bar_boundaries,
        time_signatures=piece.time_signatures,
        key_signatures=piece.key_signatures,
        clef_changes=piece.clef_changes,
        default_clefs=None if piece.source_musicxml else infer_piece_clefs(piece.notes),
        barlines=piece.barlines,
        source_musicxml=piece.source_musicxml,
    )
    model = build_score_model(score, boundaries=piece.bar_boundaries,
                              hand=case.hand)
    compact = (phrase.last_bar-phrase.first_bar+1 <= 12 and phrase.end-phrase.start <= 48)
    engraving = render_layout(score, case.first_bar, case.last_bar, case.hand,
                              total_beats=end-first, bpm=piece.bpm, continuous=compact)
    key = cache.key("native-comparison-art", score.musicxml, case.hand,
                    piece.bpm, compact, CANONICAL_CAPTURE_CONFIG) if cache is not None else ""
    atlas = assemble_layout(engraving, native_notes=True, native_model=model,
                            notation_xml=score.musicxml, cache=cache, cache_key=key)
    return {
        "capture_config": dict(CANONICAL_CAPTURE_CONFIG),
        "model": model,
        "assets": {key: atlas[key] for key in (
            "native_glyphs", "native_note_templates", "native_tie_templates",
            "native_chord_templates", "native_beam_fragments",
            "native_tuplet_fragments", "native_slur_fragments",
            "native_required_slur_pairs", "native_slurs_complete",
            "native_required_beam_groups", "native_beams_complete")},
        "first_bar": case.first_bar, "last_bar": case.last_bar,
        "sample_beats": [round(i * (end-first) / 4, 8) for i in range(4)],
        "hand": case.hand,
        "xml": score.musicxml,
        "original_xml": piece.source_musicxml if original else "",
        "source_errors": selected_source_errors(phrase, model),
    }, engraving


@lru_cache(maxsize=32)
def load_piece(path: str):
    return import_piece(Path(path))[0]

