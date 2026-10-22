"""Expressive MIDI releases must not dictate an unusable scrolling scale."""
from fractions import Fraction
from xml.etree import ElementTree as ET

import pytest

from piano_teacher.notation.lesson import DIVISIONS, build_lesson_score
from piano_teacher.lesson_validation import require_lesson_alignment
from piano_teacher.music import Note, Phrase
from piano_teacher.score import render_layout


def ornament_phrase():
    # The source ornament's two-tick release gaps and off-grid attacks are
    # taken from a 480-tick piano MIDI. These are four required attacks.
    events = ((0, 56 / 480, 82), (57 / 480, 113 / 480, 81),
              (114 / 480, 238 / 480, 79), (.5, 1, 81))
    notes = tuple(Note(start, end, pitch, 0, 0, "right", f"ornament-{i}", "melody")
                  for i, (start, end, pitch) in enumerate(events))
    return Phrase(1, 1, 1, 0, 3, notes)


def test_short_release_gaps_do_not_add_rests_or_tied_residual_notes():
    source = ornament_phrase()
    original = tuple((n.start, n.end, n.pitch, n.source_id) for n in source.notes)
    lesson = build_lesson_score(source)
    items = ET.fromstring(lesson.musicxml).findall("./part[@id='RH']/measure/note")
    sounding = [item for item in items if item.find("pitch") is not None]
    assert len(sounding) == 4
    assert [int(item.findtext("duration")) for item in sounding] == [1197, 1197, 2646, 5040]
    assert [item.findtext("type") for item in sounding] == ["32nd", "32nd", "16th", "eighth"]
    assert not any(item.find("tie") is not None for item in sounding)
    assert len(items) == 5  # Only the genuine two-beat rest after the ornament.
    # Exact ratios keep Verovio's next attack clock, despite the nearby type.
    assert Fraction(int(sounding[0].findtext("time-modification/normal-notes")),
                    int(sounding[0].findtext("time-modification/actual-notes"))) == Fraction(19, 20)
    assert lesson.phrase is source
    assert tuple((n.start, n.end, n.pitch, n.source_id) for n in source.notes) == original
    assert [(b["source_beat"], b["pitch"]) for b in lesson.note_bindings.values()
            if b["is_attack"]] == [(0, 82), (57 / 480, 81), (114 / 480, 79), (.5, 81)]


@pytest.mark.parametrize("bpm", [30, 40, 80, 120])
def test_dense_ornament_keeps_exact_required_attacks_with_bounded_native_spacing(bpm):
    pytest.importorskip("verovio")
    pytest.importorskip("music21")
    source = ornament_phrase()
    score = render_layout(build_lesson_score(source), 1, 1, total_beats=3, bpm=bpm)
    require_lesson_alignment(source, score.layout, "right")
    assert len(score.layout["attack_map"]) == 4
    attacks = [n for n in score.layout["notes"] if n["is_attack"]]
    assert [(n["source_beat"], n["pitch"]) for n in attacks] == [
        (0, 82), (57 / 480, 81), (114 / 480, 79), (.5, 81)]
    rates = [(right["x"] - left["x"]) * score.layout["widths"][left["page"]]
             / (right["beat"] - left["beat"])
             for left, right in zip(score.layout["anchors"], score.layout["anchors"][1:])
             if left["page"] == right["page"] and left["system"] == right["system"]]
    assert max(rates) < 300


def test_display_gap_cleanup_keeps_real_rests_and_stable_lanes():
    notes = (Note(0, .1166666667, 82, 0, 0, "right", "a", "first"),
             Note(.11875, .2354166667, 81, 0, 0, "right", "b", "other"),
             Note(.14, .24, 79, 0, 0, "right", "c", "first"))
    lesson = build_lesson_score(Phrase(1, 1, 1, 0, 3, notes))
    root = ET.fromstring(lesson.musicxml)
    first = root.find("./part[@id='RH']/measure/note[pitch]")
    # Another voice's nearby attack must not extend the first voice. Its own
    # following attack leaves a genuine >1/64-beat rest that must also remain.
    assert int(first.findtext("duration")) == 1176


def test_display_gap_cleanup_does_not_bridge_a_measure_boundary():
    source = Phrase(1, 1, 2, 0, 6, (
        Note(2.875, 2.995, 82, 0, 0, "right", "a", "melody"),
        Note(3.005, 3.5, 81, 0, 0, "right", "b", "melody")))
    lesson = build_lesson_score(source, boundaries=(0, 3, 6))
    root = ET.fromstring(lesson.musicxml)
    first = root.find("./part[@id='RH']/measure/note[pitch]")
    # Existing release rounding may reach the barline, but must stop there.
    assert int(first.findtext("duration")) == 1260
    assert first.find("tie") is None


@pytest.mark.parametrize("following_tick,display_end", [(1333, 1333), (1334, 1176)])
def test_display_gap_cleanup_stops_at_one_sixty_fourth_beat(following_tick, display_end):
    source = Phrase(1, 1, 1, 0, 3, (
        Note(0, 56 / 480, 82, 0, 0, "right", "a", "melody"),
        Note(following_tick / DIVISIONS, .5, 81, 0, 0, "right", "b", "melody")))
    lesson = build_lesson_score(source)
    first = ET.fromstring(lesson.musicxml).find("./part[@id='RH']/measure/note[pitch]")
    assert int(first.findtext("duration")) == display_end
