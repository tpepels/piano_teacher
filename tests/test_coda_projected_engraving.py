"""Opt-in real Verovio SVG evidence for Coda source-timed notation.

Uses the production engraving path and its independently checked source
attack mapping, not placeholder geometry or mock SVG. Does not launch Godot
or run the corpus. Original score is retained as its own source object.
"""
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from piano_teacher.application.score_artifacts import ScoreArtifacts
from piano_teacher.importing.musicxml import load_musicxml
from piano_teacher.exercise_generator import ExerciseVariant
from piano_teacher.music import Phrase
from piano_teacher.preprocessing_cache import PreprocessingCache
from piano_teacher.research.coda_reference_exercises import (
    CodaReferenceDotted,CodaReferenceChordification,CodaReferenceSlowdown,
)
from piano_teacher.research.coda_score_projection import project_coda_score


SOURCE=Path(__file__).parent/"fixtures/research/coda_four_families.musicxml"


@pytest.mark.parametrize("kind",["dotted-long","dotted-short","chord","slow-2","slow-4"])
def test_coda_real_engraving_retains_identical_note_ids_and_beat_clock(kind,tmp_path):
    piece=load_musicxml(SOURCE,bpm=80)
    original=ExerciseVariant(
        "original",Phrase(1,1,2,0,8,piece.notes),
        tuple(range(len(piece.notes))))
    if kind=="chord":
        plan=CodaReferenceChordification(8).transform(
            original,boundaries=piece.bar_boundaries,quantization=4,
            source_musicxml=piece.source_musicxml).timing
        family="chordification"
    elif kind.startswith("slow"):
        plan=CodaReferenceSlowdown(int(kind[-1])).transform(original).timing
        family="tempo-shaping"
    else:
        plan=CodaReferenceDotted(kind=="dotted-long").transform(
            original,boundaries=piece.bar_boundaries,quantization=4,
            source_musicxml=piece.source_musicxml).timing
        family="dotted-rhythms"
    stage=project_coda_score(piece,plan,reference_family=family,bpm=80,revision=5)
    artifacts=ScoreArtifacts(PreprocessingCache(tmp_path/"preproc"))
    score=artifacts.engraving(stage.selection)
    model=artifacts.source_model(stage.selection)
    expected={note.source_id for note in piece.notes}
    assert len(expected)==16
    assert set(score.layout["attack_map"])==expected
    assert score.layout["beats"]==pytest.approx(stage.tempo_map.duration_beats)
    assert score.pages
    assert len(score.pages)<8
    assert len(model["notes"])==len(expected)
    assert all(note["id"] in score.layout["attack_map"] for note in model["notes"])
    assert all(0<=glyph["x"]<=1 and 0<=glyph["y"]<=1
               for glyph in score.layout["notes"])
    output=tmp_path/"engraving-proof"
    output.mkdir(exist_ok=True)
    (output/f"{kind}.musicxml").write_text(artifacts.notation_musicxml(stage.selection))
    for i,svg in enumerate(score.pages):
        root=ET.fromstring(svg)
        assert root.tag.endswith("svg")
        assert "viewBox" in root.attrib
        assert len(list(root.iter()))>60
        (output/f"{kind}-page-{i}.svg").write_text(svg)
    # A real Verovio-derived glyph must be linked to every graded note.
    ink={glyph["source_id"] for glyph in score.layout["notes"]
         if glyph.get("is_attack")}
    assert ink==expected
