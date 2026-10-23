"""Practice tempo expands musical time without stretching engraved symbols."""
from collections import Counter
from dataclasses import replace
from statistics import mean
from xml.etree import ElementTree as ET

import pytest

from piano_teacher.notation.lesson import build_lesson_score
from piano_teacher.lesson_validation import require_lesson_alignment
from piano_teacher.music import Note, Phrase
from piano_teacher.score import render_layout


pytest.importorskip("verovio")
pytest.importorskip("music21")


def reading_phrase(*, bars=16, bar_beats=4):
    notes = [Note(float(beat), beat + 1.0, 48, 0, 0, "left")
             for beat in range(bars * bar_beats)]
    for bar in range(bars):
        start = bar * bar_beats
        notes.extend((Note(start, start + 1, 72, 0, 0, "right"),
                      Note(start, start + 1, 76, 0, 0, "right"),
                      Note(start + 1, start + 1.5, 74, 0, 0, "right"),
                      Note(start + 1.5, start + 2, 72, 0, 0, "right"),
                      Note(start + 2, start + 3, 77, 0, 0, "right")))
        if bar % 2 == 0 and bar + 1 < bars:
            notes.append(Note(start + bar_beats - 1, start + bar_beats + 1,
                              79, 0, 0, "right"))
    return Phrase(1, 1, bars, 0, bars * bar_beats, tuple(notes))


def quarter_distances_in_staff_spaces(score, bar_beats=4):
    layout = score.layout
    systems = {(system["page"], system["system"]): system
               for system in layout["systems"]}
    bass = sorted((note for note in layout["notes"] if note["pitch"] == 48),
                  key=lambda note: note["beat"])
    distances = []
    for left, right in zip(bass, bass[1:]):
        if (left["page"], left["system"]) != (right["page"], right["system"]):
            continue
        if int(left["beat"] / bar_beats) != int(right["beat"] / bar_beats):
            continue  # Barlines have a small, fixed engraving margin.
        system = systems[left["page"], left["system"]]
        staff_gap = ((system["staff_lines"][1] - system["staff_lines"][0])
                     * layout["heights"][left["page"]])
        distances.append((right["x"] - left["x"])
                         * layout["widths"][left["page"]] / staff_gap)
    return distances


def notehead_scales(score):
    scales = set()
    for page in score.pages:
        root = ET.fromstring(page)
        for group in root.iter():
            if "notehead" in group.get("class", "").split():
                for item in group:
                    if item.tag.rsplit("}", 1)[-1] == "use":
                        transform = item.get("transform", "")
                        scales.add(transform[transform.index("scale("):])
    return scales


def test_slower_tempos_spread_time_consistently_across_pages_without_stretching_notes():
    # Catches tempo-independent spacing and automatic system justification,
    # which previously changed velocity at every score system.
    phrase = reading_phrase()
    lesson = build_lesson_score(phrase)
    source_xml = ET.fromstring(lesson.musicxml)
    for measure in source_xml.findall("./part[@id='RH']/measure"):
        eighths = [note for note in measure.findall("note")
                   if note.findtext("type") == "eighth" and note.find("pitch") is not None]
        for note, state in zip(eighths, ("begin", "end")):
            ET.SubElement(note, "beam", number="1").text = state
    lesson = replace(lesson, musicxml=ET.tostring(source_xml, encoding="unicode"))
    distances = {}
    glyph_scales = []
    for bpm in (30, 40, 80, 120):
        score = render_layout(lesson, 1, 16, total_beats=64, bpm=bpm)
        require_lesson_alignment(phrase, score.layout, "both")
        assert score.layout["strip_trim_repeated_headers"] is True
        assert len(score.pages) >= 2
        assert max(Counter(system["page"] for system in score.layout["systems"]).values()) <= 2
        assert all(len(system["staff_lines"]) == 10 for system in score.layout["systems"])
        gaps = quarter_distances_in_staff_spaces(score)
        assert len(gaps) >= 40
        # Dense chords, ties and rest glyphs retain native collision clearance.
        assert max(gaps) / min(gaps) < 1.1
        distances[bpm] = mean(gaps)
        glyph_scales.append(notehead_scales(score))
        assert all(0 <= note["x"] <= 1 and 0 <= note["y"] <= 1
                   for note in score.layout["notes"])
        assert any("class=\"tie\"" in page for page in score.pages)
        assert any("class=\"beam\"" in page for page in score.pages)
        assert any("class=\"rest\"" in page for page in score.pages)
    assert distances[30] / distances[120] == pytest.approx(4, rel=.02)
    assert distances[40] / distances[80] == pytest.approx(2, rel=.02)
    assert glyph_scales[0] and all(scales == glyph_scales[0] for scales in glyph_scales)


def test_slow_wide_measures_remain_inside_bounded_pages():
    phrase = reading_phrase(bars=10, bar_beats=8)
    lesson = build_lesson_score(phrase)
    score = render_layout(lesson, 1, 10, total_beats=80, bpm=12)
    require_lesson_alignment(phrase, score.layout, "both")
    assert len(score.pages) == 5
    assert all(height < 700 for height in score.layout["heights"])
    assert all(0 <= anchor["x"] <= 1 for anchor in score.layout["anchors"])
    assert all(system["right"] < 1 for system in score.layout["systems"])
    gaps = quarter_distances_in_staff_spaces(score, bar_beats=8)
    assert max(gaps) / min(gaps) < 1.01


@pytest.mark.parametrize("bpm", [0, -40, float("nan"), float("inf")])
def test_invalid_reading_tempo_fails_clearly(bpm):
    phrase = reading_phrase(bars=1)
    with pytest.raises(ValueError, match="tempo"):
        render_layout(build_lesson_score(phrase), 1, 1, total_beats=4, bpm=bpm)


@pytest.mark.parametrize("subdivisions,bpm", [(4, 120), (2, 300), (8, 80), (16, 40)])
def test_dense_chromatic_measures_fit_after_native_collision_spacing(subdivisions, bpm):
    # Natural note spacing also needs room for accidentals and flags. A time
    # budget alone previously clipped up to half of these engraved systems.
    notes = tuple(Note(index / subdivisions, (index + 1) / subdivisions,
                       60 + index % 12, 0, 0, "right")
                  for index in range(64 * subdivisions))
    phrase = Phrase(1, 1, 16, 0, 64, notes)
    lesson = build_lesson_score(phrase)
    score = render_layout(lesson, 1, 16, total_beats=64, bpm=bpm)
    require_lesson_alignment(phrase, score.layout, "right")
    assert max(system["right"] for system in score.layout["systems"]) < 1
    assert all(0 <= note["x"] <= 1 for note in score.layout["notes"])
    assert all(0 <= anchor["x"] <= 1 for anchor in score.layout["anchors"])
    assert max(Counter(system["page"] for system in score.layout["systems"]).values()) <= 2
    ordinary = render_layout(lesson, 1, 16, total_beats=64)
    assert notehead_scales(score) == notehead_scales(ordinary)
