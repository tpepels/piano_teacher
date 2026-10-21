"""Grace notation is source fidelity, not an additional scored MIDI attack."""
from dataclasses import replace
from xml.etree import ElementTree as ET

from piano_teacher.importing.musicxml import load_musicxml
from piano_teacher.music import Phrase
from piano_teacher.notation.lesson import build_lesson_score
from piano_teacher.notation.model import build_score_model


def _source(tmp_path, *, slash="no"):
    xml = """<score-partwise version="4.0">
      <part-list>
        <score-part id="RH"><part-name>Right hand</part-name></score-part>
        <score-part id="LH"><part-name>Left hand</part-name></score-part>
      </part-list>
      <part id="RH"><measure number="1"><attributes><divisions>10080</divisions>
        <time><beats>4</beats><beat-type>4</beat-type></time></attributes>
        <note><grace slash="%s"/><pitch><step>B</step><octave>4</octave></pitch>
          <type>eighth</type><voice>1</voice></note>
        <note><pitch><step>C</step><octave>5</octave></pitch>
          <duration>10080</duration><voice>1</voice><type>quarter</type></note>
        <note><rest/><duration>30240</duration><type>half</type><dot/></note>
      </measure></part>
      <part id="LH"><measure number="1"><attributes><divisions>10080</divisions>
        <time><beats>4</beats><beat-type>4</beat-type></time></attributes>
        <note><pitch><step>C</step><octave>3</octave></pitch>
          <duration>40320</duration><type>whole</type></note>
      </measure></part></score-partwise>""" % slash
    path = tmp_path / "grace.musicxml"
    path.write_text(xml)
    return load_musicxml(path, bpm=80)


def _lesson(piece, notes):
    phrase = Phrase(1, 1, 1, 0, 4, tuple(notes))
    return build_lesson_score(phrase, boundaries=piece.bar_boundaries,
        time_signatures=piece.time_signatures, clef_changes=piece.clef_changes,
        source_musicxml=piece.source_musicxml)


def test_un_slashed_grace_is_natively_drawable_but_never_graded(tmp_path):
    piece = _source(tmp_path)
    assert len(piece.notes) == 2
    assert {(n.start, n.end) for n in piece.notes} == {(0, 1), (0, 4)}
    score = _lesson(piece, piece.notes)
    root = ET.fromstring(score.musicxml)
    all_graces = root.findall(".//note/grace")
    assert len(all_graces) == 1
    assert score.unrendered_expressions == ()
    model = build_score_model(score, boundaries=piece.bar_boundaries)
    assert len(model["notes"]) == 2
    assert len(model["grace_notes"]) == 1
    grace = model["grace_notes"][0]
    assert grace["hand"] == "right"
    assert grace["beat"] == 0.0
    assert grace["spelling"] == {"step": "B", "alter": 0, "octave": 4}
    assert grace["note_type"] == "eighth"
    assert grace["before_note_id"] in {s["id"] for s in model["notation_events"]
                                       if s["is_attack"]}
    assert len([s for s in model["notation_events"] if s["is_attack"]]) == 2

    left = _lesson(piece, [n for n in piece.notes if n.hand == "left"])
    assert not ET.fromstring(left.musicxml).findall(".//grace")
    assert not build_score_model(left, boundaries=piece.bar_boundaries)["grace_notes"]


def test_slashed_grace_uses_original_verovio_fallback_without_disappearing(tmp_path):
    piece = _source(tmp_path, slash="yes")
    score = _lesson(piece, piece.notes)
    assert "note:grace" in score.unrendered_expressions
    assert len(ET.fromstring(score.musicxml).findall(".//grace")) == 1
    model = build_score_model(score, boundaries=piece.bar_boundaries)
    assert model["unrendered_expressions"] == ["note:grace"]
    assert model["grace_notes"] == []
    assert len(model["notes"]) == 2


def test_real_verovio_grace_engraving_keeps_only_scored_source_anchors(tmp_path):
    from piano_teacher.score import render_layout

    for slash in ("no", "yes"):
        piece = _source(tmp_path, slash=slash)
        score = _lesson(piece, piece.notes)
        engraved = render_layout(score, 1, 1, "both",
            total_beats=4, bpm=80)
        assert engraved.pages and "<svg" in engraved.pages[0]
        assert len(engraved.layout["notes"]) == 2
        assert {item["source_id"] for item in engraved.layout["notes"]} == {
            note.source_id for note in piece.notes}
