"""Source crescendo/decrescendo directions become native structural wedges."""
from dataclasses import replace
from xml.etree import ElementTree as ET

from piano_teacher.importing.musicxml import load_musicxml
from piano_teacher.music import Phrase
from piano_teacher.notation.lesson import build_lesson_score
from piano_teacher.notation.model import build_score_model


SOURCE = """<score-partwise version="4.0">
  <part-list>
    <score-part id="RH"><part-name>Right hand</part-name></score-part>
    <score-part id="LH"><part-name>Left hand</part-name></score-part>
  </part-list>
  <part id="RH">
    <measure number="1">
      <attributes><divisions>10080</divisions>
        <time><beats>4</beats><beat-type>4</beat-type></time></attributes>
      <direction placement="below"><direction-type>
        <wedge type="crescendo" number="2"/></direction-type></direction>
      <note><pitch><step>C</step><octave>5</octave></pitch>
        <duration>40320</duration><type>whole</type></note>
    </measure>
    <measure number="2">
      <direction placement="below"><direction-type>
        <wedge type="stop" number="2"/></direction-type></direction>
      <note><pitch><step>D</step><octave>5</octave></pitch>
        <duration>40320</duration><type>whole</type></note>
    </measure>
  </part>
  <part id="LH">
    <measure number="1">
      <attributes><divisions>10080</divisions>
        <time><beats>4</beats><beat-type>4</beat-type></time></attributes>
      <note><pitch><step>C</step><octave>3</octave></pitch>
        <duration>40320</duration><type>whole</type></note>
    </measure>
    <measure number="2">
      <note><pitch><step>G</step><octave>3</octave></pitch>
        <duration>40320</duration><type>whole</type></note>
    </measure>
  </part>
</score-partwise>"""


def _load(tmp_path, xml=SOURCE):
    file = tmp_path / "wedge.musicxml"
    file.write_text(xml, encoding="utf-8")
    return load_musicxml(file, bpm=100)


def _lesson(piece, notes):
    phrase = Phrase(1, 1, 2, 0, 8, tuple(notes))
    return build_lesson_score(
        phrase, boundaries=piece.bar_boundaries,
        time_signatures=piece.time_signatures,
        source_musicxml=piece.source_musicxml)


def test_native_wedge_preserves_source_endpoints_and_timing(tmp_path):
    piece = _load(tmp_path)
    assert len(piece.notes) == 4
    score = _lesson(piece, piece.notes)
    assert score.unrendered_expressions == ()
    assert len(ET.fromstring(score.musicxml).findall(".//wedge")) == 2
    model = build_score_model(score, boundaries=piece.bar_boundaries)
    assert model["unrendered_expressions"] == []
    assert [
        (mark["kind"], mark["value"], mark["number"], mark["hand"], mark["beat"])
        for mark in model["expressions"]
    ] == [
        ("hairpin", "crescendo", "2", "right", 0.0),
        ("hairpin", "stop", "2", "right", 4.0),
    ]
    assert model["duration_beats"] == 8
    assert len(model["notes"]) == 4
    assert len([e for e in model["notation_events"] if e["is_attack"]]) == 4
    # Wedges for an omitted hand must not leak into a simplified LH lesson.
    left_score = _lesson(piece, [n for n in piece.notes if n.hand == "left"])
    assert not ET.fromstring(left_score.musicxml).findall(".//wedge")
    assert not [e for e in build_score_model(
        left_score, boundaries=piece.bar_boundaries)["expressions"]
        if e["kind"] == "hairpin"]


def test_unmatched_wedge_retains_complete_original_verovio_fallback(tmp_path):
    root = ET.fromstring(SOURCE)
    wedge = root.find("./part[@id='RH']/measure[@number='2']/direction")
    root.find("./part[@id='RH']/measure[@number='2']").remove(wedge)
    piece = _load(tmp_path, ET.tostring(root, encoding="unicode"))
    score = _lesson(piece, piece.notes)
    assert len(ET.fromstring(score.musicxml).findall(".//wedge")) == 1
    assert "direction:wedge" in score.unrendered_expressions
    assert "direction:wedge" in build_score_model(
        score, boundaries=piece.bar_boundaries)["unrendered_expressions"]


def test_unsupported_wedge_geometry_keeps_legacy_fallback(tmp_path):
    root = ET.fromstring(SOURCE)
    root.find(".//wedge").set("niente", "yes")
    piece = _load(tmp_path, ET.tostring(root, encoding="unicode"))
    score = _lesson(piece, piece.notes)
    assert "direction:wedge" in score.unrendered_expressions


def test_diminuendo_is_preserved_as_distinct_native_opening(tmp_path):
    root = ET.fromstring(SOURCE)
    root.find(".//wedge").set("type", "diminuendo")
    piece = _load(tmp_path, ET.tostring(root, encoding="unicode"))
    score = _lesson(piece, piece.notes)
    model = build_score_model(score, boundaries=piece.bar_boundaries)
    assert [(m["value"],m["beat"]) for m in model["expressions"]
            if m["kind"] == "hairpin"] == [("diminuendo", 0.0), ("stop", 4.0)]
    assert not model["unrendered_expressions"]
