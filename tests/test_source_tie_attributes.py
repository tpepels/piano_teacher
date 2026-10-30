"""Source-authored tie placement must survive the MusicXML import/lesson roundtrip."""
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from piano_teacher.importing.musicxml import load_musicxml
from piano_teacher.music import Phrase
from piano_teacher.notation.lesson import build_lesson_score
from piano_teacher.notation.model import build_score_model


SOURCE = Path(__file__).parent / "fixtures/musical_fidelity/xml_chord_ties.musicxml"


def _piece(tmp_path, *, start_style: dict, stop_style: dict):
    root = ET.parse(SOURCE).getroot()
    for i, measure in enumerate(root.findall("./part/measure")):
        for note in measure.findall("note"):
            if note.find("pitch") is None:
                continue
            notations = ET.SubElement(note, "notations")
            ET.SubElement(notations, "tied", {"type": "start" if i == 0 else "stop",
                                             **(start_style if i == 0 else stop_style)})
    path = tmp_path / "authored_ties.musicxml"
    path.write_text(ET.tostring(root, encoding="unicode"))
    return load_musicxml(path, bpm=80)


def _render(piece):
    phrase = Phrase(1, 1, 2, 0., 8., piece.notes)
    score = build_lesson_score(phrase, boundaries=piece.bar_boundaries,
                               time_signatures=piece.time_signatures,
                               source_musicxml=piece.source_musicxml)
    root = ET.fromstring(score.musicxml)
    model = build_score_model(score, boundaries=piece.bar_boundaries)
    return root, model, score


def test_both_tie_endpoints_retain_authored_placement_across_barline(tmp_path):
    piece = _piece(tmp_path, start_style={"placement":"above"},
                   stop_style={"placement":"above"})
    root, model, score = _render(piece)
    for measure_index, expected in ((0, "above"), (1, "above")):
        notes = root.findall("./part[@id='RH']/measure")[measure_index].findall("note")
        notes = [n for n in notes if n.find("pitch") is not None]
        assert len(notes) == 3
        assert {m.get("placement") for n in notes
                for m in n.findall("notations/tied")} == {expected}
    marks = [e["tied_marks"] for e in model["notation_events"]
             if e["kind"] == "note"]
    assert len(marks) == 6
    assert all(len(m) == 1 and any(x[0] == "placement" for x in m[0])
               for m in marks)
    assert "note:tied" not in score.unrendered_expressions
    assert len(piece.notes) == 3  # A sounded tie is one graded attack.


def test_incompatible_authored_endpoint_placements_request_fallback(tmp_path):
    piece = _piece(tmp_path, start_style={"placement":"above"},
                   stop_style={"placement":"below"})
    root, _model, score = _render(piece)
    assert {mark.get("placement") for mark in root.findall(".//notations/tied")} == {
        "above", "below"}
    assert "note:tied" in score.unrendered_expressions


def test_complex_authored_tie_style_is_preserved_but_not_claimed_native(tmp_path):
    piece = _piece(tmp_path,
        start_style={"placement":"above", "line-type":"dashed", "orientation":"over"},
        stop_style={"placement":"below", "color":"#ff0000"})
    root, _model, score = _render(piece)
    tags = root.findall(".//notations/tied")
    assert any(tag.get("line-type") == "dashed" for tag in tags)
    assert any(tag.get("color") == "#ff0000" for tag in tags)
    assert "note:tied" in score.unrendered_expressions


def test_no_authored_tie_style_is_invented_for_sound_only_source(tmp_path):
    source = load_musicxml(SOURCE, bpm=80)
    _, model, score = _render(source)
    assert all(all(len(mark) == 1 and mark[0][0] == "type"
                   for mark in e["tied_marks"])
               for e in model["notation_events"] if e["tied_marks"])
    assert "note:tied" not in score.unrendered_expressions


def test_polyphonic_authored_ties_match_their_own_voice_after_backup(tmp_path):
    root = ET.Element("score-partwise", version="4.0")
    part_list = ET.SubElement(root, "part-list")
    score_part = ET.SubElement(part_list, "score-part", id="P1")
    ET.SubElement(score_part, "part-name").text = "Right Hand"
    part = ET.SubElement(root, "part", id="P1")

    def note(measure, step, duration, voice, kind, placement):
        element = ET.SubElement(measure, "note")
        pitch = ET.SubElement(element, "pitch")
        ET.SubElement(pitch, "step").text = step
        ET.SubElement(pitch, "octave").text = "4"
        ET.SubElement(element, "duration").text = str(duration)
        ET.SubElement(element, "tie", type=kind)
        ET.SubElement(element, "voice").text = voice
        ET.SubElement(element, "type").text = (
            "whole" if duration == 16 else "half")
        notation = ET.SubElement(element, "notations")
        ET.SubElement(notation, "tied", type=kind, placement=placement)

    for measure_number in (1, 2):
        measure = ET.SubElement(part, "measure", number=str(measure_number))
        if measure_number == 1:
            attributes = ET.SubElement(measure, "attributes")
            ET.SubElement(attributes, "divisions").text = "4"
            meter = ET.SubElement(attributes, "time")
            ET.SubElement(meter, "beats").text = "4"
            ET.SubElement(meter, "beat-type").text = "4"
        kind = "start" if measure_number == 1 else "stop"
        duration = 16 if measure_number == 1 else 8
        note(measure, "C", duration, "1", kind, "above")
        if duration == 8:
            rest = ET.SubElement(measure, "note")
            ET.SubElement(rest, "rest")
            ET.SubElement(rest, "duration").text = "8"
            ET.SubElement(rest, "voice").text = "1"
        backup = ET.SubElement(measure, "backup")
        ET.SubElement(backup, "duration").text = "16"
        note(measure, "E", duration, "2", kind, "below")
        if duration == 8:
            rest = ET.SubElement(measure, "note")
            ET.SubElement(rest, "rest")
            ET.SubElement(rest, "duration").text = "8"
            ET.SubElement(rest, "voice").text = "2"

    path = tmp_path / "two_voices.musicxml"
    path.write_text(ET.tostring(root, encoding="unicode"))
    piece = load_musicxml(path, bpm=80)
    score_root, _model, score = _render(piece)
    placement_by_note = {}
    for element in score_root.findall(".//note"):
        pitch = element.findtext("pitch/step")
        marks = element.findall("notations/tied")
        if marks:
            placement_by_note.setdefault(pitch, set()).update(
                mark.get("placement") for mark in marks)
    assert placement_by_note == {"C": {"above"}, "E": {"below"}}
    assert "note:tied" not in score.unrendered_expressions
    assert len(piece.notes) == 2
