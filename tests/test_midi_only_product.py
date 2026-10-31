"""MIDI-only acceptance contracts for the desktop product.

Generated lesson XML is an internal engraving format, not a user-supplied
MusicXML dependency. No physical hardware or long-running raster audit.
"""
from pathlib import Path

import pytest

from piano_teacher.application.score_artifacts import ScoreArtifacts, ScoreSelection
from piano_teacher.importing.pieces import import_piece
from piano_teacher.learning import LearningPlan
from piano_teacher.preprocessing_cache import PreprocessingCache

FIXTURES = Path(__file__).parent / "fixtures" / "musical_fidelity"


@pytest.mark.parametrize("filename", [
    "midi_four_four.mid",
    "midi_mixed_meter.mid",
    "midi_triplets.mid",
])
def test_midi_is_sufficient_for_import_lesson_and_semantic_notation(filename, tmp_path):
    piece, source_notation = import_piece(FIXTURES / filename)
    assert source_notation is None
    assert piece.source_musicxml == ""
    assert piece.notes and piece.phrases
    assert all(note.source_id.startswith("midi-t") for note in piece.notes)

    plan = LearningPlan(piece, exercise_strategy="coda-part",
                        timing_strategy="dotted-long-short",
                        tempo_strategy="two-phase-tempo")
    assert plan.lesson_steps
    phrase = piece.phrases[0]
    selected = ScoreSelection(piece, phrase, "both", "midi-only-acceptance",
                              1, filename)
    artifacts = ScoreArtifacts(PreprocessingCache(tmp_path / "cache"))
    model = artifacts.source_model(selected)
    expected = {note.source_id for note in phrase.notes}
    assert len(model["notes"]) == len(phrase.notes)
    assert {note["id"] for note in model["notes"]} == expected
    lesson_xml = artifacts.notation_musicxml(selected)
    assert "<score-partwise" in lesson_xml
    assert lesson_xml != piece.source_musicxml
