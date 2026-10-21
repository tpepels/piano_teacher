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
    assert {"note:articulations","note:ornaments",
            "direction:dynamics","direction:pedal"}.issubset(score.unrendered_expressions)
    model = build_score_model(score,boundaries=piece.bar_boundaries)
    assert len(model["notes"]) == len(piece.notes)
    assert len([n for n in model["notation_events"] if n["kind"] == "note"]) == 3
    assert len(model["unrendered_expressions"]) == 4


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
