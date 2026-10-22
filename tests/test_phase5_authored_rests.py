"""Authored rests survive projection; reconstructed voice padding stays hidden."""
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from piano_teacher.importing.musicxml import load_musicxml
from piano_teacher.music import Note, Phrase
from piano_teacher.notation.lesson import DIVISIONS, build_lesson_score
from piano_teacher.notation.model import build_score_model
from piano_teacher.notation.semantic_contract import verify_musicxml_contract


FIXTURES = Path(__file__).parent / "fixtures/musical_fidelity"


def compile_source(path):
    piece = load_musicxml(path, bpm=80)
    phrase = Phrase(1, 1, len(piece.bar_boundaries) - 1,
                    piece.bar_boundaries[0], piece.bar_boundaries[-1], piece.notes)
    score = build_lesson_score(
        phrase, boundaries=piece.bar_boundaries,
        time_signatures=piece.time_signatures, key_signatures=piece.key_signatures,
        clef_changes=piece.clef_changes, barlines=piece.barlines,
        source_musicxml=piece.source_musicxml)
    return piece, score


@pytest.mark.parametrize("hand", ["both", "right", "left"])
@pytest.mark.parametrize("source_id,onset,duration,dots", [
    ("xml-p0-m0-e3", 0, 2, 0),
    ("xml-p0-m1-e4", 1, 3, 1),
])
def test_parallel_tied_voices_preserve_exact_original_rest_contracts(
        hand, source_id, onset, duration, dots):
    path = FIXTURES / "xml_parallel_tied_voices.musicxml"
    piece, score = compile_source(path)
    model = build_score_model(score, boundaries=piece.bar_boundaries, hand=hand)
    report = verify_musicxml_contract(path.read_text(), score.musicxml, model, hand=hand)
    # Literal expectations come from the original score's written voice 2,
    # not from generated notation or a renderer's inferred silence.
    rows = [row for row in report["elements"]
            if row["construct"] == "written_rests"
            and row["source"]["id"] == source_id
            and row["boundary"].startswith("original->")]
    assert {row["boundary"] for row in rows} == {
        "original->generated", "original->native"}
    assert all(row["status"] == "verified" for row in rows), rows
    for row in rows:
        assert row["actual"]["visible"] is True
        assert row["actual"]["onset"] == onset
        assert row["actual"]["duration"] == duration
        assert row["actual"]["note_type"] == "half"
        assert row["actual"]["dots"] == dots
    assert report["passed"], report["discrepancies"]


def test_authored_trailing_rest_measures_survive_without_pitched_attacks():
    path = FIXTURES / "xml_trailing_rests.musicxml"
    piece, score = compile_source(path)
    model = build_score_model(score, boundaries=piece.bar_boundaries)
    report = verify_musicxml_contract(path.read_text(), score.musicxml, model)
    assert report["passed"], report["discrepancies"]
    rests = [event for event in model["notation_events"]
             if event["staff"] == "right" and event["kind"] == "rest"]
    assert [(event["beat"], event["duration_beats"], event["dots"])
            for event in rests] == [(1, 3, 1), (4, 4, 0), (8, 4, 0)]


def test_authored_full_measure_rest_keeps_whole_glyph_in_three_four(tmp_path):
    path = tmp_path / 'measure-rest.musicxml'
    path.write_text('''<score-partwise><part-list><score-part id="RH">
    <part-name>Right Hand</part-name></score-part></part-list><part id="RH">
    <measure number="1"><attributes><divisions>1</divisions>
    <time><beats>3</beats><beat-type>4</beat-type></time>
    <clef><sign>G</sign><line>2</line></clef></attributes>
    <note><pitch><step>C</step><octave>4</octave></pitch><duration>3</duration>
    <voice>1</voice><type>half</type><dot/></note><backup><duration>3</duration></backup>
    <note><rest measure="yes"/><duration>3</duration><voice>2</voice><type>whole</type></note>
    </measure></part></score-partwise>''')
    piece, score = compile_source(path)
    rest_note = ET.fromstring(score.musicxml).find('./part[@id="RH"]/measure/note[rest]')
    assert rest_note.findtext('type')=='whole'
    assert rest_note.find('rest').get('measure')=='yes'
    assert not rest_note.findall('dot')
    assert rest_note.findtext('duration')==str(3*DIVISIONS)
    model = build_score_model(score, boundaries=piece.bar_boundaries)
    report = verify_musicxml_contract(path.read_text(),score.musicxml,model)
    assert report['passed'],report['discrepancies']


def write_source(tmp_path, voice_two):
    path = tmp_path / "authored.musicxml"
    path.write_text('''<score-partwise><part-list><score-part id="P0">
    <part-name>Right Hand</part-name></score-part></part-list><part id="P0">
    <measure number="1"><attributes><divisions>96</divisions>
    <time><beats>4</beats><beat-type>4</beat-type></time>
    <clef><sign>G</sign><line>2</line></clef></attributes>
    <note><pitch><step>C</step><octave>4</octave></pitch><duration>384</duration>
    <voice>1</voice><type>whole</type></note><backup><duration>384</duration>
    </backup>''' + voice_two + '</measure></part></score-partwise>')
    return path


def test_authored_micro_rest_is_not_consumed_by_midi_release_cleanup(tmp_path):
    path = write_source(tmp_path, '''
    <note><rest/><duration>96</duration><voice>2</voice><type>quarter</type></note>
    <note><pitch><step>E</step><octave>4</octave></pitch><duration>95</duration>
    <voice>2</voice><type>quarter</type><time-modification><actual-notes>96</actual-notes>
    <normal-notes>95</normal-notes></time-modification></note>
    <note><rest/><duration>1</duration><voice>2</voice><type>128th</type>
    <time-modification><actual-notes>3</actual-notes><normal-notes>1</normal-notes>
    </time-modification></note>
    <note><pitch><step>G</step><octave>4</octave></pitch><duration>192</duration>
    <voice>2</voice><type>half</type></note>''')
    _, score = compile_source(path)
    root = ET.fromstring(score.musicxml)
    measure = root.find("./part[@id='RH']/measure")
    voice = next(note.findtext("voice") for note in measure.findall("note")
                 if note.findtext("pitch/step") == "E")
    notes = measure.findall(f"note[voice='{voice}']")
    assert [(int(note.findtext("duration")), note.find("rest") is not None)
            for note in notes] == [(10080, True), (9975, False), (105, True), (20160, False)]
    assert notes[0].get("print-object") != "no"
    assert notes[2].get("print-object") != "no"


@pytest.mark.parametrize("hidden", [False, True])
def test_consecutive_authored_secondary_rests_keep_segmentation_and_visibility(tmp_path, hidden):
    visibility = ' print-object="no"' if hidden else ''
    path = write_source(tmp_path, f'''
    <note><rest/><duration>96</duration><voice>2</voice><type>quarter</type></note>
    <note><pitch><step>E</step><octave>4</octave></pitch><duration>96</duration>
    <voice>2</voice><type>quarter</type></note>
    <note{visibility}><rest/><duration>96</duration><voice>2</voice><type>quarter</type></note>
    <note><rest/><duration>96</duration><voice>2</voice><type>quarter</type></note>''')
    _, score = compile_source(path)
    measure = ET.fromstring(score.musicxml).find("./part[@id='RH']/measure")
    voice = next(note.findtext("voice") for note in measure.findall("note")
                 if note.findtext("pitch/step") == "E")
    notes = measure.findall(f"note[voice='{voice}']")
    rests = [note for note in notes if note.find("rest") is not None]
    assert [(note.findtext("type"), int(note.findtext("duration")),
             note.get("print-object") == "no") for note in rests] == [
        ("quarter", DIVISIONS, False), ("quarter", DIVISIONS, hidden),
        ("quarter", DIVISIONS, False)]


def test_source_xml_forward_gaps_are_synthetic_padding_not_authored_rests(tmp_path):
    path = write_source(tmp_path, '''
    <forward><duration>96</duration><voice>2</voice></forward>
    <note><pitch><step>E</step><octave>4</octave></pitch><duration>96</duration>
    <voice>2</voice><type>quarter</type></note>
    <forward><duration>192</duration><voice>2</voice></forward>''')
    _, score = compile_source(path)
    notes = ET.fromstring(score.musicxml).findall("./part[@id='RH']/measure/note[voice='2']")
    rests = [note for note in notes if note.find("rest") is not None]
    assert [int(note.findtext("duration")) for note in rests] == [DIVISIONS, 2 * DIVISIONS]
    assert all(note.get("print-object") == "no" for note in rests)


def test_synthetic_secondary_voice_padding_stays_hidden():
    phrase = Phrase(1, 1, 1, 0, 4, (
        Note(0, 4, 60, 0, 0, "right", "sustain", "1"),
        Note(1, 2, 64, 0, 0, "right", "overlap", "2")))
    score = build_lesson_score(phrase)
    notes = ET.fromstring(score.musicxml).findall("./part[@id='RH']/measure/note[voice='2']")
    rests = [note for note in notes if note.find("rest") is not None]
    assert [int(note.findtext("duration")) for note in rests] == [DIVISIONS, 2 * DIVISIONS]
    assert all(note.get("print-object") == "no" for note in rests)


def test_performance_micro_gap_stays_hidden():
    phrase = Phrase(1, 1, 1, 0, 4, (
        Note(0, .625, 60, 0, 0, "right", "a", "melody"),
        Note(.75, 4, 64, 0, 0, "right", "b", "melody")))
    score = build_lesson_score(phrase)
    rests = [note for note in ET.fromstring(score.musicxml).findall("./part[@id='RH']/measure/note")
             if note.find("rest") is not None]
    assert len(rests) == 1
    assert int(rests[0].findtext("duration")) == DIVISIONS // 8
    assert rests[0].get("print-object") == "no"


@pytest.mark.parametrize("hand", ["both", "right", "left"])
@pytest.mark.parametrize("layout,rest_hand", [
    ("same-staff", "right"), ("named-part", "left"), ("grand-staff", "left"),
])
def test_rest_only_voice_preserves_authored_rests_with_scoped_staff_ownership(
        tmp_path, hand, layout, rest_hand):
    # Namespaced input and repeated raw voice labels cannot route by XML id,
    # voice number alone, or a fabricated pitched anchor for the empty voice.
    attrs = '''<attributes><divisions>1</divisions><time><beats>4</beats>
    <beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes>'''
    pitched = '''<note><pitch><step>C</step><octave>5</octave></pitch>
    <duration>4</duration><voice>7</voice><type>whole</type><staff>1</staff></note>'''
    rest_staff = "2" if layout == "grand-staff" else "1"
    rest_voice = "8" if layout == "same-staff" else "7"
    rests = f'''<note><rest/><duration>1</duration><voice>{rest_voice}</voice>
    <type>quarter</type><staff>{rest_staff}</staff></note>
    <note><rest/><duration>3</duration><voice>{rest_voice}</voice>
    <type>half</type><dot/><staff>{rest_staff}</staff></note>'''
    if layout == "named-part":
        part_list = '''<score-part id="source[upper]"><part-name>Right Hand</part-name>
        </score-part><score-part id="source'lower"><part-name>Left Hand</part-name></score-part>'''
        parts = f'''<part id="source[upper]"><measure number="1">{attrs}{pitched}</measure></part>
        <part id="source'lower"><measure number="1">{attrs.replace('<sign>G</sign><line>2</line>', '<sign>F</sign><line>4</line>')}
        {rests}</measure></part>'''
    else:
        part_name = "Piano" if layout == "grand-staff" else "Right Hand"
        part_list = f'''<score-part id="source'part"><part-name>{part_name}</part-name></score-part>'''
        if layout == "grand-staff":
            attrs = attrs.replace('</attributes>', '''<clef number="2"><sign>F</sign>
            <line>4</line></clef></attributes>''')
        parts = f'''<part id="source'part"><measure number="1">{attrs}{pitched}
        <backup><duration>4</duration></backup>{rests}</measure></part>'''
    path = tmp_path / "rest-only.musicxml"
    path.write_text(f'''<score-partwise xmlns="http://www.musicxml.org/ns/musicxml">
    <part-list>{part_list}</part-list>{parts}</score-partwise>''')
    piece, score = compile_source(path)
    model = build_score_model(score, boundaries=piece.bar_boundaries, hand=hand)
    rests = [event for event in model["notation_events"]
             if event["kind"] == "rest" and event["staff"] == rest_hand]
    assert [(event["beat"], event["duration_beats"], event["note_type"], event["dots"])
            for event in rests] == [(0, 1, "quarter", 0), (1, 3, "half", 1)]
    assert len({event["voice"] for event in rests}) == 1
    assert {binding["source_id"] for binding in score.note_bindings.values()} == {"xml-p0-m0-e1"}
    report = verify_musicxml_contract(path.read_text(), score.musicxml, model, hand=hand)
    assert report["passed"], report["discrepancies"]


@pytest.mark.parametrize("hand", ["both", "right", "left"])
@pytest.mark.parametrize("rest_staff", ["1", "2"])
def test_phrase_subset_keeps_rests_when_voice_pitches_are_outside_phrase(tmp_path, hand, rest_staff):
    path = write_source(tmp_path, '''
    <note><pitch><step>E</step><octave>4</octave></pitch><duration>384</duration>
    <voice>2</voice><type>whole</type></note>''')
    original = ET.parse(path).getroot()
    if rest_staff == "2":
        original.find("part-list/score-part/part-name").text = "Piano"
        attributes = original.find("part/measure/attributes")
        attributes.append(ET.fromstring('<clef number="2"><sign>F</sign><line>4</line></clef>'))
        outside_note = original.find("part/measure/note[voice='2']")
        outside_note.find("pitch/step").text = "C"
        outside_note.find("pitch/octave").text = "3"
        ET.SubElement(outside_note, "staff").text = "2"
    original.find("part").append(ET.fromstring(f'''<measure number="2">
    <note><pitch><step>C</step><octave>4</octave></pitch><duration>384</duration>
    <voice>1</voice><type>whole</type></note><backup><duration>384</duration></backup>
    <note><rest/><duration>96</duration><voice>2</voice><type>quarter</type><staff>{rest_staff}</staff></note>
    <note><rest/><duration>288</duration><voice>2</voice><type>half</type><dot/><staff>{rest_staff}</staff></note>
    </measure>'''))
    path.write_text(ET.tostring(original, encoding="unicode"))
    piece = load_musicxml(path, bpm=80)
    phrase = Phrase(2, 2, 2, 4, 8, tuple(note for note in piece.notes if note.start >= 4))
    assert {note.voice for note in phrase.notes} == {"xml-p0-s1-v1"}
    score = build_lesson_score(phrase, boundaries=piece.bar_boundaries,
        time_signatures=piece.time_signatures, clef_changes=piece.clef_changes,
        source_musicxml=piece.source_musicxml)
    model = build_score_model(score, boundaries=piece.bar_boundaries, hand=hand)
    rest_hand = "left" if rest_staff == "2" else "right"
    rests = [event for event in model["notation_events"]
             if event["staff"] == rest_hand and event["kind"] == "rest"]
    assert [(event["beat"], event["duration_beats"], event["dots"])
            for event in rests] == [(0, 1, 0), (1, 3, 1)]
    assert len({event["voice"] for event in rests}) == 1
    assert {binding["source_id"] for binding in score.note_bindings.values()} == {"xml-p0-m1-e0"}
    assert [event["midi_pitch"] for event in model["notation_events"]
            if event["kind"] == "note"] == [60]


def test_multiple_rest_only_voices_keep_distinct_lanes(tmp_path):
    path = write_source(tmp_path, '''
    <note><rest/><duration>96</duration><voice>2</voice><type>quarter</type></note>
    <note><rest/><duration>288</duration><voice>2</voice><type>half</type><dot/></note>
    <backup><duration>384</duration></backup>
    <note><rest/><duration>192</duration><voice>3</voice><type>half</type></note>
    <note><rest/><duration>192</duration><voice>3</voice><type>half</type></note>''')
    piece, score = compile_source(path)
    model = build_score_model(score, boundaries=piece.bar_boundaries)
    rests = [event for event in model["notation_events"]
             if event["kind"] == "rest" and event["staff"] == "right"]
    assert [(event["beat"], event["duration_beats"], event["dots"])
            for event in rests] == [(0, 1, 0), (1, 3, 1), (0, 2, 0), (2, 2, 0)]
    assert len({event["voice"] for event in rests}) == 2
    report = verify_musicxml_contract(path.read_text(), score.musicxml, model)
    assert report["passed"], report["discrepancies"]


def test_rest_ownership_accepts_imported_decimal_pitch_alteration(tmp_path):
    path = write_source(tmp_path, '''
    <note><rest/><duration>96</duration><voice>2</voice><type>quarter</type></note>
    <note><rest/><duration>288</duration><voice>2</voice><type>half</type><dot/></note>''')
    root = ET.parse(path).getroot()
    ET.SubElement(root.find("part/measure/note/pitch"), "alter").text = "0.0"
    path.write_text(ET.tostring(root, encoding="unicode"))
    piece, score = compile_source(path)
    model = build_score_model(score, boundaries=piece.bar_boundaries)
    rests = [event for event in model["notation_events"]
             if event["kind"] == "rest" and event["staff"] == "right"]
    assert [(event["beat"], event["duration_beats"])
            for event in rests] == [(0, 1), (1, 3)]
