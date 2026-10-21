"""Source expression projection into both graded and simplified lesson scores."""
from xml.etree import ElementTree as ET

from piano_teacher.importing.musicxml import load_musicxml
from piano_teacher.music import Phrase
from piano_teacher.notation.lesson import build_lesson_score
from piano_teacher.notation.model import build_score_model


def _decorated_piece(tmp_path):
    # An independent MusicXML fixture: two right notes, one left note.
    # Import IDs must reflect the *actual* source order, not a guessed beat.
    xml = """<score-partwise version="4.0"><part-list>
    <score-part id="RH"><part-name>Right hand</part-name></score-part>
    <score-part id="LH"><part-name>Left hand</part-name></score-part>
    </part-list>
    <part id="RH"><measure number="1">
      <attributes><divisions>10080</divisions><time><beats>4</beats>
      <beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes>
      <direction placement="below"><direction-type><dynamics><p/></dynamics></direction-type></direction>
      <direction><direction-type><pedal type="start"/></direction-type></direction>
      <note><pitch><step>C</step><octave>5</octave></pitch>
        <duration>10080</duration><voice>1</voice><type>quarter</type>
        <notations><articulations><staccato/></articulations>
        <ornaments><turn/></ornaments><slur number="1" type="start"/></notations></note>
      <note><rest/><duration>10080</duration><voice>1</voice><type>quarter</type></note>
      <note><pitch><step>E</step><octave>5</octave></pitch>
        <duration>10080</duration><voice>1</voice><type>quarter</type>
        <notations><slur number="1" type="stop"/></notations></note>
      <note><rest/><duration>10080</duration><voice>1</voice><type>quarter</type></note>
    </measure></part>
    <part id="LH"><measure number="1">
      <attributes><divisions>10080</divisions><time><beats>4</beats>
      <beat-type>4</beat-type></time><clef><sign>F</sign><line>4</line></clef></attributes>
      <note><pitch><step>C</step><octave>3</octave></pitch>
        <duration>40320</duration><voice>1</voice><type>whole</type></note>
    </measure></part></score-partwise>"""
    path = tmp_path / "marked.musicxml"
    path.write_text(xml)
    return load_musicxml(path, bpm=80)


def _lesson(piece, notes):
    phrase = Phrase(1,1,1,0,4,tuple(notes))
    lesson = build_lesson_score(phrase,boundaries=piece.bar_boundaries,
        time_signatures=piece.time_signatures,key_signatures=piece.key_signatures,
        clef_changes=piece.clef_changes,source_musicxml=piece.source_musicxml)
    return lesson,ET.fromstring(lesson.musicxml)


def test_complete_source_markings_project_to_matching_generated_notes(tmp_path):
    piece = _decorated_piece(tmp_path)
    score, root = _lesson(piece,piece.notes)
    notes = root.findall("./part[@id='RH']/measure/note")
    first = next(note for note in notes if note.findtext("pitch/step") == "C")
    last = next(note for note in notes if note.findtext("pitch/step") == "E")
    assert first.find("./notations/articulations/staccato") is not None
    assert first.find("./notations/ornaments/turn") is not None
    assert first.find("./notations/slur[@type='start']") is not None
    assert last.find("./notations/slur[@type='stop']") is not None
    assert root.find("./part[@id='RH']/measure/direction/direction-type/dynamics/p") is not None
    assert root.find("./part[@id='RH']/measure/direction/direction-type/pedal") is not None
    assert not root.findall("./part[@id='LH']/measure/direction")
    assert score.unrendered_expressions == ("note:ornaments",)
    model = build_score_model(score,boundaries=piece.bar_boundaries)
    assert len(model["notes"]) == len(piece.notes)
    assert len([n for n in model["notation_events"] if n["kind"] == "note"]) == 3
    assert model["unrendered_expressions"] == ["note:ornaments"]
    assert {(mark["kind"], mark["value"]) for mark in model["expressions"]} == {
        ("articulation", "staccato"), ("dynamic", "p"), ("pedal", "start")}


def test_simplified_variant_drops_unpaired_slurs_and_omitted_hand_markings(tmp_path):
    piece = _decorated_piece(tmp_path)
    right = [n for n in piece.notes if n.hand == "right"]
    score, root = _lesson(piece,right[:1])
    assert not root.findall(".//slur")  # Second endpoint was omitted.
    assert root.find("./part[@id='RH']/measure/note/notations/articulations/staccato") is not None
    assert root.find("./part[@id='RH']/measure/direction/direction-type/dynamics/p") is not None
    assert len(score.note_bindings) == 1
    model = build_score_model(score,boundaries=piece.bar_boundaries)
    assert len(model["notes"]) == 1
    assert model["notes"][0]["midi_pitch"] == 72

    left_score,left_root = _lesson(piece, [n for n in piece.notes if n.hand=="left"])
    assert left_score.unrendered_expressions == ()
    assert not left_root.findall(".//slur")
    assert not left_root.findall(".//direction")
    assert len(build_score_model(left_score,boundaries=piece.bar_boundaries)["notes"]) == 1


def test_unannotated_musicxml_compilation_remains_unchanged(tmp_path):
    piece = _decorated_piece(tmp_path)
    phrase = Phrase(1,1,1,0,4,piece.notes)
    unannotated = build_lesson_score(phrase,boundaries=piece.bar_boundaries,
        time_signatures=piece.time_signatures)
    assert unannotated.unrendered_expressions == ()
    assert build_score_model(unannotated,boundaries=piece.bar_boundaries)["unrendered_expressions"] == []


def test_imported_markup_does_not_modify_original_source_data(tmp_path):
    piece = _decorated_piece(tmp_path)
    original = piece.source_musicxml
    _lesson(piece,piece.notes)
    _lesson(piece,piece.notes[:1])
    assert piece.source_musicxml == original

def test_projected_expressions_render_through_real_verovio(tmp_path):
    from piano_teacher.score import render_layout
    piece = _decorated_piece(tmp_path)
    score, _ = _lesson(piece,piece.notes)
    engraving = render_layout(score,1,1,"both",
                              total_beats=4,bpm=80)
    assert engraving.pages
    assert any("svg" in page for page in engraving.pages)
    assert len(engraving.layout["notes"]) == 3


def test_unstaffed_voice_directions_follow_the_correct_grand_staff_hand(tmp_path):
    # A single MusicXML piano part contains two independent voices/staves.
    # Directions specify a voice but do not repeat its staff number.
    xml = """<score-partwise version="4.0">
      <part-list><score-part id="P1"><part-name>Piano</part-name></score-part></part-list>
      <part id="P1"><measure number="1">
        <attributes><divisions>10080</divisions>
          <time><beats>4</beats><beat-type>4</beat-type></time>
          <staves>2</staves>
          <clef number="1"><sign>G</sign><line>2</line></clef>
          <clef number="2"><sign>F</sign><line>4</line></clef>
        </attributes>
        <direction><direction-type><dynamics><p/></dynamics></direction-type>
          <voice>1</voice></direction>
        <direction><direction-type><dynamics><mf/></dynamics></direction-type>
          </direction>
        <note><pitch><step>C</step><octave>5</octave></pitch>
          <duration>40320</duration><voice>1</voice><type>whole</type><staff>1</staff></note>
        <backup><duration>40320</duration></backup>
        <direction><direction-type><dynamics><f/></dynamics></direction-type>
          <voice>2</voice></direction>
        <note><pitch><step>C</step><octave>3</octave></pitch>
          <duration>40320</duration><voice>2</voice><type>whole</type><staff>2</staff></note>
      </measure></part></score-partwise>"""
    path = tmp_path / "piano-voices.musicxml"
    path.write_text(xml, encoding="utf-8")
    piece = load_musicxml(path, bpm=80)
    assert {n.hand for n in piece.notes} == {"left", "right"}

    full, root = _lesson(piece, piece.notes)
    assert root.find("./part[@id='RH']/measure/direction/direction-type/dynamics/p") is not None
    assert root.find("./part[@id='LH']/measure/direction/direction-type/dynamics/f") is not None
    assert root.find(".//direction-type/dynamics/mf") is None
    assert "direction:dynamics" in full.unrendered_expressions

    # Omitting the right-hand attack must not send its expression to the left.
    left = tuple(n for n in piece.notes if n.hand == "left")
    _, simplified = _lesson(piece, left)
    assert simplified.find("./part[@id='LH']/measure/direction/direction-type/dynamics/f") is not None
    assert simplified.find(".//direction-type/dynamics/p") is None


def test_native_expressions_survive_as_ungraded_beat_anchored_events(tmp_path):
    piece = _decorated_piece(tmp_path)
    # Remove the deliberately unsupported ornament from the fixture. A score
    # containing ONLY supported marks must keep the native renderer enabled.
    from dataclasses import replace
    source = piece.source_musicxml.replace("<ornaments><turn/></ornaments>", "")
    piece = replace(piece, source_musicxml=source)
    score, root = _lesson(piece, piece.notes)
    assert score.unrendered_expressions == ()
    model = build_score_model(score, boundaries=piece.bar_boundaries)
    assert model["unrendered_expressions"] == []
    marks = model["expressions"]
    assert {(m["kind"], m["value"], m["hand"], m["beat"])
            for m in marks} == {
        ("articulation", "staccato", "right", 0.0),
        ("dynamic", "p", "right", 0.0),
        ("pedal", "start", "right", 0.0),
    }
    assert len(model["notes"]) == 3  # No expressive mark is a graded note.
    assert len([x for x in model["notation_events"]
                if x["kind"] == "note" and x["is_attack"]]) == 3


def test_unknown_musical_directions_keep_full_verovio_fallback(tmp_path):
    piece = _decorated_piece(tmp_path)
    from dataclasses import replace
    source = piece.source_musicxml.replace(
        "<dynamics><p/></dynamics>", "<dynamics><other-dynamics>subito</other-dynamics></dynamics>")
    piece = replace(piece, source_musicxml=source)
    score, _ = _lesson(piece, piece.notes)
    assert "direction:dynamics" in score.unrendered_expressions
    assert "note:ornaments" in score.unrendered_expressions
    assert not any(m["kind"] == "dynamic" for m in
                   build_score_model(score, boundaries=piece.bar_boundaries)["expressions"])

