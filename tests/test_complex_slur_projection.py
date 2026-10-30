"""Complex authored slur projections retain exact source head/voice ownership."""
from xml.etree import ElementTree as ET

from piano_teacher.importing.musicxml import load_musicxml
from piano_teacher.music import Phrase
from piano_teacher.notation.lesson import build_lesson_score
from piano_teacher.notation.assets.slurs import slur_pairs_from_xml


def render(tmp_path, xml):
    source = tmp_path / "voice_slurs.musicxml"
    source.write_text(ET.tostring(xml, encoding="unicode"))
    piece = load_musicxml(source, bpm=76)
    phrase = Phrase(1, 1, len(piece.bar_boundaries)-1,
                    piece.bar_boundaries[0], piece.bar_boundaries[-1],
                    piece.notes)
    score = build_lesson_score(phrase, boundaries=piece.bar_boundaries,
                               time_signatures=piece.time_signatures,
                               source_musicxml=piece.source_musicxml)
    return piece, score, ET.fromstring(score.musicxml)


def _note(parent, step, octave, duration, staff, role, *, number="1", chord=False):
    node = ET.SubElement(parent, "note")
    if chord:
        ET.SubElement(node, "chord")
    pitch = ET.SubElement(node, "pitch")
    ET.SubElement(pitch, "step").text = step
    ET.SubElement(pitch, "octave").text = str(octave)
    ET.SubElement(node, "duration").text = str(duration)
    ET.SubElement(node, "voice").text = "1"
    ET.SubElement(node, "type").text = "whole" if duration == 16 else "half" if duration == 8 else "quarter"
    ET.SubElement(node, "staff").text = str(staff)
    if role:
        marks = ET.SubElement(node, "notations")
        ET.SubElement(marks, "slur", type=role, number=number)
    return node


def test_simultaneous_same_number_slurs_on_two_staves_do_not_cross_pair(tmp_path):
    root = ET.Element("score-partwise")
    part_list = ET.SubElement(root, "part-list")
    entry = ET.SubElement(part_list, "score-part", id="P1")
    ET.SubElement(entry, "part-name").text = "Piano"
    part = ET.SubElement(root, "part", id="P1")
    bar = ET.SubElement(part, "measure", number="1")
    attrs = ET.SubElement(bar, "attributes")
    ET.SubElement(attrs, "divisions").text = "4"
    meter = ET.SubElement(attrs, "time")
    ET.SubElement(meter, "beats").text = "4"
    ET.SubElement(meter, "beat-type").text = "4"
    ET.SubElement(attrs, "staves").text = "2"
    for index, sign, line in ((1,"G",2),(2,"F",4)):
        clef = ET.SubElement(attrs, "clef", number=str(index))
        ET.SubElement(clef, "sign").text = sign
        ET.SubElement(clef, "line").text = str(line)
    # Both slurs open in measure 1, before either closes in measure 2.
    # The same voice and slur number are legitimate on different staves.
    for bar_number in (1, 2):
        if bar_number == 2:
            bar = ET.SubElement(part, "measure", number="2")
        for staff, step in ((1, "C" if bar_number == 1 else "D"),
                            (2, "G" if bar_number == 1 else "A")):
            if staff == 2:
                backup = ET.SubElement(bar, "backup")
                ET.SubElement(backup, "duration").text = "16"
            _note(bar, step, 5 if staff == 1 else 3, 16, staff,
                  "start" if bar_number == 1 else "stop")
    piece, score, generated = render(tmp_path, root)
    assert len(piece.notes) == 4
    assert not score.unrendered_expressions
    for hand, start, stop in (("RH","C","D"),("LH","G","A")):
        notes = generated.findall(f"./part[@id='{hand}']/measure/note")
        actual = [(n.findtext("pitch/step"), mark.get("type"))
                  for n in notes for mark in n.findall("notations/slur")]
        assert actual == [(start, "start"), (stop, "stop")]
    assert len(slur_pairs_from_xml(score.musicxml)) == 2


def test_three_tone_chord_slur_reanchors_to_last_retained_pitch(tmp_path):
    root = ET.Element("score-partwise")
    listing = ET.SubElement(root, "part-list")
    ET.SubElement(ET.SubElement(listing,"score-part",id="RH"),"part-name").text="Right Hand"
    part = ET.SubElement(root, "part", id="RH")
    measure = ET.SubElement(part, "measure", number="1")
    attrs = ET.SubElement(measure, "attributes")
    ET.SubElement(attrs,"divisions").text="4"
    meter = ET.SubElement(attrs,"time")
    ET.SubElement(meter,"beats").text="4"
    ET.SubElement(meter,"beat-type").text="4"
    for i,step in enumerate(("C","E","G")):
        _note(measure, step, 4, 4, 1, "start" if i==0 else None,
              chord=(i>0))
    _note(measure, "A", 4, 4, 1, None)
    _note(measure, "B", 4, 4, 1, None)
    # Need a fourth quarter so the source measure remains 4/4.
    final = _note(measure, "C", 5, 4, 1, "stop")
    piece, _, full = render(tmp_path, root)
    assert len(piece.notes) == 6
    original_start = next(n for n in piece.notes if n.pitch == 60)
    last_chord_tone = next(n for n in piece.notes if n.pitch == 67)
    trimmed = tuple(n for n in piece.notes if n not in
                    (original_start, next(n for n in piece.notes if n.pitch == 64)))
    phrase = Phrase(1, 1, 1, 0., 4., trimmed)
    score = build_lesson_score(phrase, boundaries=piece.bar_boundaries,
                               time_signatures=piece.time_signatures,
                               source_musicxml=piece.source_musicxml)
    generated = ET.fromstring(score.musicxml)
    marks = [(e.findtext("pitch/step"), mark.get("type"))
             for e in generated.findall(".//note")
             for mark in e.findall("notations/slur")]
    assert ("G", "start") in marks
    assert ("C", "stop") in marks
    assert not any(x[0] in ("E",) for x in marks)
    assert last_chord_tone in phrase.notes
