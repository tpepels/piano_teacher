"""Source-accurate single/double/terminal/repeat barlines in the semantic model."""
from dataclasses import replace
from xml.etree import ElementTree as ET

import pytest

from piano_teacher.lesson_score import build_lesson_score
from piano_teacher.music import Note, Phrase
from piano_teacher.score_model import build_score_model


def score():
    notes = (
        Note(0, 1, 72, 0, 0, "right", "right1"),
        Note(2, 3, 74, 0, 0, "right", "right2"),
        Note(0, 1, 48, 0, 0, "left", "left1"),
        Note(2, 3, 50, 0, 0, "left", "left2"),
    )
    phrase = Phrase(1, 1, 2, 0, 4, notes)
    return build_lesson_score(phrase, boundaries=(0, 2, 4),
                              time_signatures=((0, 2, 4),))


def with_barlines(lesson, edits):
    root = ET.fromstring(lesson.musicxml)
    for part, measure_index, location, style, direction in edits:
        measure = root.findall(f"./part[@id='{part}']/measure")[measure_index]
        barline = ET.SubElement(measure, "barline", location=location)
        if style is not None:
            ET.SubElement(barline, "bar-style").text = style
        if direction:
            ET.SubElement(barline, "repeat", direction=direction)
    return replace(lesson, musicxml=ET.tostring(root, encoding="unicode"))


def test_regular_boundaries_and_final_bar_exist_without_source_tags():
    result = build_score_model(score(), boundaries=(0, 2, 4))
    assert [(m["start_beat"], m["end_beat"]) for m in result["measures"]] == [
        (0, 2), (2, 4)]
    assert all(m["left_barline"] is None for m in result["measures"])
    assert [m["right_barline"] for m in result["measures"]] == [
        {"style":"regular", "repeat":""},
        {"style":"regular", "repeat":""}]
    assert {n["id"] for n in result["notes"]} == {
        "right1", "right2", "left1", "left2"}


@pytest.mark.parametrize("style", [
    "regular", "light-light", "light-heavy", "heavy-light",
    "heavy-heavy", "heavy", "none", "dashed", "dotted",
])
def test_musicxml_explicit_styles_preserve_source_beat_and_all_notes(style):
    original = score()
    changed = with_barlines(original, [
        ("RH", 0, "right", style, ""),
        ("LH", 0, "right", style, "")])
    before = build_score_model(original, boundaries=(0, 2, 4))
    after = build_score_model(changed, boundaries=(0, 2, 4))
    assert after["measures"][0]["right_barline"] == {
        "style": style, "repeat": ""}
    assert after["notes"] == before["notes"]
    assert after["notation_events"] == before["notation_events"]


def test_forward_backward_and_shared_repeat_barline_metadata():
    changed = with_barlines(score(), [
        ("RH", 0, "left", None, "forward"),
        ("LH", 0, "left", None, "forward"),
        ("RH", 0, "right", None, "backward"),
        ("LH", 0, "right", None, "backward"),
        ("RH", 1, "left", None, "forward"),
        ("LH", 1, "left", None, "forward"),
        ("RH", 1, "right", "light-heavy", "backward"),
        ("LH", 1, "right", "light-heavy", "backward")])
    measures = build_score_model(changed, boundaries=(0, 2, 4))["measures"]
    assert measures[0]["left_barline"] == {
        "style":"heavy-light", "repeat":"forward"}
    assert measures[0]["right_barline"] == {
        "style":"light-heavy", "repeat":"backward"}
    assert measures[1]["left_barline"] == measures[0]["left_barline"]
    assert measures[1]["right_barline"]["style"] == "light-heavy"


def test_conflicting_grand_staff_barlines_fail_instead_of_mismatching_hands():
    changed = with_barlines(score(), [
        ("RH", 0, "right", "light-heavy", ""),
        ("LH", 0, "right", "light-light", "")])
    with pytest.raises(ValueError, match="Inconsistent barlines"):
        build_score_model(changed, boundaries=(0, 2, 4))


@pytest.mark.parametrize("location,style", [
    ("middle", "regular"), ("right", "tick"), ("right", "short"),
])
def test_unsupported_barlines_are_never_silently_drawn(location, style):
    changed = with_barlines(score(), [
        ("RH", 0, location, style, "")])
    with pytest.raises(ValueError, match="Unsupported MusicXML barline"):
        build_score_model(changed, boundaries=(0, 2, 4))


def test_volta_ending_is_not_dropped_by_native_semantic_score():
    original = score()
    root = ET.fromstring(original.musicxml)
    measure = root.findall("./part[@id='RH']/measure")[0]
    barline = ET.SubElement(measure, "barline", location="right")
    ET.SubElement(barline, "ending", number="1", type="start")
    changed = replace(original, musicxml=ET.tostring(root, encoding="unicode"))
    with pytest.raises(ValueError, match="Volta endings"):
        build_score_model(changed, boundaries=(0, 2, 4))
