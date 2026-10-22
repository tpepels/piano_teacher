"""Conservative guard for removing repeated printed-system headers.

These tests inspect real generated MusicXML, not a replacement engraving or
game simulation. Godot's separate renderer test checks the actual PNG ink.
"""
from xml.etree import ElementTree as ET

from piano_teacher.notation.lesson import build_lesson_score
from piano_teacher.music import Note, Phrase
from piano_teacher.score import _can_remove_repeated_system_headers


def _lesson():
    notes = tuple(
        Note(float(i), float(i + 1), 60 + i % 5, 0, 0, "right")
        for i in range(8)
    )
    notes += tuple(
        Note(float(i), float(i + 1), 48, 0, 0, "left")
        for i in range(8)
    )
    return build_lesson_score(Phrase(1, 1, 2, 0, 8, notes))


def test_repeated_headers_are_only_optional_for_bound_stable_piano_parts():
    lesson = _lesson()
    assert _can_remove_repeated_system_headers(
        lesson.musicxml, lesson.note_bindings
    )
    # Imported MusicXML has no strict source attack/clef guarantee.
    assert not _can_remove_repeated_system_headers(lesson.musicxml, None)


def test_key_meter_clef_and_written_navigation_never_get_cropped():
    lesson = _lesson()
    for kind in ("key", "time", "clef", "direction", "barline"):
        root = ET.fromstring(lesson.musicxml)
        second = root.find("./part[@id='RH']/measure[@number='2']")
        assert second is not None
        if kind in ("key", "time", "clef"):
            attributes = ET.Element("attributes")
            element = ET.SubElement(attributes, kind)
            ET.SubElement(element, "fifths" if kind == "key" else
                          "beats" if kind == "time" else "sign").text = (
                              "2" if kind != "clef" else "F"
                          )
            second.insert(0, attributes)
        else:
            second.insert(0, ET.Element(kind))
        assert not _can_remove_repeated_system_headers(
            ET.tostring(root, encoding="unicode"), lesson.note_bindings
        ), kind


def test_nonstandard_parts_keep_all_headers():
    lesson = _lesson()
    root = ET.fromstring(lesson.musicxml)
    root.find("part").set("id", "P1")
    assert not _can_remove_repeated_system_headers(
        ET.tostring(root, encoding="unicode"), lesson.note_bindings
    )
