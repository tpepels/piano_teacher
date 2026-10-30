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
                   stop_style={"placement":"below"})
    root, model, score = _render(piece)
    for measure_index, expected in ((0, "above"), (1, "below")):
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
