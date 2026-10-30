"""Step 3: source-authored engraving survives eligible dotted retiming.

The fixtures combine real imported tied attacks with authored slurs, rests,
beams and a positioned dynamic. No physical MIDI or full corpus audit.
"""
from dataclasses import replace
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from piano_teacher.exercise_contracts import ConstantTempo, DottedPairTiming
from piano_teacher.exercise_generator import ExerciseVariant
from piano_teacher.exercise_pipeline import ExercisePipeline
from piano_teacher.exercise_strategies import ExerciseContext, LegacyStrategy
from piano_teacher.importing.musicxml import load_musicxml
from piano_teacher.music import Phrase, source_note_id
from piano_teacher.notation.lesson import build_lesson_score
from piano_teacher.notation.model import build_score_model
from piano_teacher.notation.rhythm_safety import rhythm_protected_source_ids


def _authored_score(tmp_path):
    root = ET.Element("score-partwise", version="4.0")
    partlist = ET.SubElement(root, "part-list")
    part_id = "P1"
    score_part = ET.SubElement(partlist, "score-part", id=part_id)
    ET.SubElement(score_part, "part-name").text = "Right hand"
    part = ET.SubElement(root, "part", id=part_id)

    def note(measure, pitch=None, *, duration, kind, dot=False,
             tie=None, slur=None, beam=None, articulation=None, fingering=None,
             placement=None):
        tag = ET.SubElement(measure, "note")
        if pitch is None:
            ET.SubElement(tag, "rest")
        else:
            p = ET.SubElement(tag, "pitch")
            ET.SubElement(p, "step").text = pitch[0]
            ET.SubElement(p, "octave").text = pitch[1]
        ET.SubElement(tag, "duration").text = str(duration)
        ET.SubElement(tag, "voice").text = "1"
        ET.SubElement(tag, "type").text = kind
        if dot:
            ET.SubElement(tag, "dot")
        if tie:
            ET.SubElement(tag, "tie", type=tie)
        if beam:
            ET.SubElement(tag, "beam", number="1").text = beam
        if slur or tie or articulation or fingering:
            notations = ET.SubElement(tag, "notations")
            if tie:
                options = {"type": tie}
                if placement:
                    options["placement"] = placement
                ET.SubElement(notations, "tied", **options)
            if slur:
                ET.SubElement(notations, "slur", type=slur, number="1")
            if articulation:
                ET.SubElement(ET.SubElement(notations, "articulations"),
                              articulation)
            if fingering:
                ET.SubElement(ET.SubElement(notations, "technical"),
                              "fingering").text = fingering
        return tag

    measure = ET.SubElement(part, "measure", number="1")
    attributes = ET.SubElement(measure, "attributes")
    ET.SubElement(attributes, "divisions").text = "10080"
    time = ET.SubElement(attributes, "time")
    ET.SubElement(time, "beats").text = "4"
    ET.SubElement(time, "beat-type").text = "4"
    clef = ET.SubElement(attributes, "clef")
    ET.SubElement(clef, "sign").text = "G"
    ET.SubElement(clef, "line").text = "2"
    for i, pitch in enumerate(("C", "D", "E", "F", "G", "A", "B", "C")):
        if i == 1:
            direction = ET.SubElement(measure, "direction", placement="below")
            ET.SubElement(ET.SubElement(direction, "direction-type"),
                          "dynamics").append(ET.Element("mf"))
            ET.SubElement(direction, "voice").text = "1"
        note(measure, (pitch, "5" if i == 7 else "4"),
             duration=5040, kind="eighth",
             slur=("start" if i == 0 else "stop" if i == 7 else None),
             beam=("begin" if i % 4 == 0 else "end" if i % 4 == 3 else "continue"),
             articulation="staccato" if i == 0 else None,
             fingering="2" if i == 2 else None)

    measure = ET.SubElement(part, "measure", number="2")
    note(measure, ("D", "4"), duration=40320, kind="whole",
         tie="start", placement="below")
    measure = ET.SubElement(part, "measure", number="3")
    note(measure, ("D", "4"), duration=10080, kind="quarter",
         tie="stop", placement="below")
    note(measure, duration=30240, kind="half", dot=True)

    filename = tmp_path / "authored.musicxml"
    filename.write_text(ET.tostring(root, encoding="unicode"), encoding="utf-8")
    return filename


def _exercise(piece):
    phrase = Phrase(1, 1, 3, piece.bar_boundaries[0],
                    piece.bar_boundaries[-1], piece.notes)
    original = ExerciseVariant("original", phrase,
                               tuple(range(len(phrase.notes))))
    pipeline = ExercisePipeline(LegacyStrategy(), DottedPairTiming(), ConstantTempo())
    stages = pipeline.build(
        ExerciseContext(phrase, "right"), lambda: (original,),
        source_musicxml=piece.source_musicxml)
    transformed = next(stage for stage in stages if stage.transformed_rhythm)
    return phrase, transformed.variant.phrase


def test_dotted_score_preserves_source_slurs_rests_ties_fingering_and_dynamics(tmp_path):
    piece = load_musicxml(_authored_score(tmp_path), bpm=80)
    original, changed = _exercise(piece)
    assert len(changed.notes) == len(original.notes)
    assert changed.notes[1].start == pytest.approx(.75)
    assert changed.notes[-1].start == pytest.approx(4)
    assert changed.notes[-1].end == pytest.approx(9)
    score = build_lesson_score(
        changed, boundaries=piece.bar_boundaries,
        time_signatures=piece.time_signatures,
        key_signatures=piece.key_signatures,
        clef_changes=piece.clef_changes,
        source_musicxml=piece.source_musicxml, retimed_source=True)
    root = ET.fromstring(score.musicxml)
    marks = root.findall(".//notations/slur")
    assert sorted(mark.get("type") for mark in marks) == ["start", "stop"]
    assert root.find(".//articulations/staccato") is not None
    assert root.find(".//technical/fingering").text == "2"
    assert root.find(".//direction/direction-type/dynamics/mf") is not None
    direction = root.find(".//part/measure[@number='1']/direction")
    assert int(direction.findtext("offset")) == 7560

    rests = root.findall(".//part/measure[@number='3']/note[rest]")
    assert any(rest.findtext("duration") == "30240"
               and rest.findtext("type") == "half"
               and rest.find("dot") is not None for rest in rests)
    source_ties = [n for n in root.findall(".//note")
                   if n.find("notations/tied") is not None]
    assert {mark.get("type") for n in source_ties
            for mark in n.findall("notations/tied")} >= {"start", "stop"}
    assert all(mark.get("placement") == "below"
               for n in source_ties for mark in n.findall("notations/tied"))

    model = build_score_model(score, boundaries=piece.bar_boundaries)
    assert {n["id"] for n in model["notes"]} == {
        source_note_id(note, i) for i, note in enumerate(original.notes)}
    assert next(n for n in model["notes"]
                if n["id"] == original.notes[1].source_id)["onset_beats"] == pytest.approx(.75)


def test_authored_tuplets_are_ineligible_for_dotted_transform_without_loss():
    source = Path(__file__).parent / "fixtures/connector_pixels/tuplets/score.musicxml"
    piece = load_musicxml(source, bpm=80)
    phrase = Phrase(1, 1, len(piece.bar_boundaries) - 1,
                    piece.bar_boundaries[0], piece.bar_boundaries[-1], piece.notes)
    original = ExerciseVariant("original", phrase, tuple(range(len(phrase.notes))))
    pipeline = ExercisePipeline(LegacyStrategy(), DottedPairTiming(), ConstantTempo())
    stages = pipeline.build(
        ExerciseContext(phrase, "right"), lambda: (original,),
        source_musicxml=piece.source_musicxml)
    assert not any(stage.transformed_rhythm for stage in stages)
    assert rhythm_protected_source_ids(piece.source_musicxml)
    score = build_lesson_score(
        phrase, boundaries=piece.bar_boundaries,
        time_signatures=piece.time_signatures,
        source_musicxml=piece.source_musicxml)
    assert "time-modification" in score.musicxml


def test_source_tie_chain_remains_immutable_when_dotted_stage_is_available(tmp_path):
    piece = load_musicxml(_authored_score(tmp_path), bpm=80)
    original, changed = _exercise(piece)
    source_note = original.notes[-1]
    transformed = changed.notes[-1]
    assert transformed.source_id == source_note.source_id
    assert (transformed.start, transformed.end) == (
        source_note.start, source_note.end)
    assert source_note.source_id in rhythm_protected_source_ids(
        piece.source_musicxml)
