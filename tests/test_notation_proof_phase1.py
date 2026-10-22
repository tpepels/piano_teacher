"""Phase 1 regression and mutation tests for the independent notation oracle."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from piano_teacher.music import Phrase
from piano_teacher.notation.lesson import build_lesson_score
from piano_teacher.notation.model import build_score_model
from piano_teacher.notation.proof import (
    read_written_score, verify_generated_engraving, verify_original_musicxml,
)
from piano_teacher.score import import_piece


FIXTURES = Path(__file__).parent / "fixtures" / "musical_fidelity"
SCORES = (
    "xml_chord_ties.musicxml",
    "xml_grandstaff_voices.musicxml",
    "xml_keys_spelling.musicxml",
    "xml_quintuplets.musicxml",
)


def _full_original(filename: str):
    path = FIXTURES / filename
    piece, _ = import_piece(path)
    phrase = Phrase(1, 1, len(piece.bar_boundaries) - 1, 0,
                    piece.bar_boundaries[-1], piece.notes)
    lesson = build_lesson_score(
        phrase, boundaries=piece.bar_boundaries,
        time_signatures=piece.time_signatures,
        key_signatures=piece.key_signatures,
        clef_changes=piece.clef_changes,
        barlines=piece.barlines,
        source_musicxml=piece.source_musicxml,
    )
    return path.read_text(), lesson.musicxml, build_score_model(
        lesson, boundaries=piece.bar_boundaries,
    )


@pytest.mark.parametrize("filename", SCORES)
def test_original_score_attacks_and_explicit_attributes_survive_to_native_model(filename):
    original, generated, model = _full_original(filename)
    evidence = verify_original_musicxml(original, model)
    assert evidence["source_attacks"] == len(model["notes"])
    assert evidence["source_written_symbols"] > 0
    assert evidence["passed"], evidence["errors"]


@pytest.mark.parametrize("filename", SCORES)
def test_every_generated_written_symbol_survives_native_model(filename):
    original, generated, model = _full_original(filename)
    evidence = verify_generated_engraving(generated, model)
    assert evidence["expected_symbols"] == evidence["native_symbols"]
    assert evidence["passed"], evidence["errors"]


@pytest.mark.parametrize("field,value", [
    ("midi_pitch", 127),
    ("onset_beats", 2.75),
    ("duration_beats", 0.25),
    ("spelling", ["F", 1, 5]),
])
def test_source_oracle_detects_mutated_imported_note(field, value):
    source, _, model = _full_original("xml_keys_spelling.musicxml")
    corrupted = deepcopy(model)
    corrupted["notes"][0][field] = value
    result = verify_original_musicxml(source, corrupted)
    assert not result["passed"]
    assert "original attacks" in result["errors"][0]


@pytest.mark.parametrize("field,value", [
    ("meter", [7, 8]),
    ("keys", {"right": 6}),
    ("clefs", {"right": {"sign": "F", "line": 4, "octave_change": 0}}),
])
def test_source_oracle_detects_mutated_measure_metadata(field, value):
    source, _, model = _full_original("xml_keys_spelling.musicxml")
    corrupted = deepcopy(model)
    if field == "keys":
        corrupted["measures"][0]["keys"].update(value)
    elif field == "clefs":
        corrupted["measures"][0]["clefs"].update(value)
    else:
        corrupted["measures"][0][field] = value
    assert not verify_original_musicxml(source, corrupted)["passed"]


@pytest.mark.parametrize("field,value", [
    ("beat", 0.375),
    ("duration_beats", 0.125),
    ("voice", "wrong"),
    ("note_type", "64th"),
    ("dots", 3),
    ("accidental", "sharp"),
    ("tie_start", True),
    ("staff", "left"),
])
def test_native_symbol_oracle_detects_deliberate_notation_corruption(field, value):
    _, generated, model = _full_original("xml_keys_spelling.musicxml")
    corrupted = deepcopy(model)
    event = next(e for e in corrupted["notation_events"] if e["kind"] == "note")
    event[field] = value
    result = verify_generated_engraving(generated, corrupted)
    assert not result["passed"]
    assert "engraving symbols" in result["errors"][0]


def test_native_symbol_oracle_detects_missing_rest_and_duplicate_note():
    _, generated, model = _full_original("xml_chord_ties.musicxml")
    assert verify_generated_engraving(generated, model)["passed"]
    corrupted = deepcopy(model)
    rests = [e for e in corrupted["notation_events"] if e["kind"] == "rest"]
    assert rests
    corrupted["notation_events"].remove(rests[0])
    assert not verify_generated_engraving(generated, corrupted)["passed"]
    corrupted = deepcopy(model)
    note = next(e for e in corrupted["notation_events"] if e["kind"] == "note")
    corrupted["notation_events"].append(deepcopy(note))
    assert not verify_generated_engraving(generated, corrupted)["passed"]


def test_mutating_original_xml_is_detected_without_changing_generated_score():
    original, _, model = _full_original("xml_keys_spelling.musicxml")
    assert verify_original_musicxml(original, model)["passed"]
    altered = original.replace("<step>D</step>", "<step>F</step>", 1)
    assert altered != original
    result = verify_original_musicxml(altered, model)
    assert not result["passed"]


def test_original_parser_collapses_written_ties_but_keeps_each_chord_attack():
    original = (FIXTURES / "xml_chord_ties.musicxml").read_text()
    facts = read_written_score(original)
    assert len(facts.notes) == 3
    assert sorted(n[2] for n in facts.notes) == [6.0, 6.0, 6.0]
    assert len([e for e in facts.symbols if e["kind"] == "rest"]) == 1
