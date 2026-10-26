"""Derived practice silence must never change the canonical source events."""
from copy import deepcopy
import json

import pytest

from piano_teacher.music import ClefChange, KeySignature, Note, Phrase
from piano_teacher.notation.lesson import build_lesson_score
from piano_teacher.notation.model import build_score_model


def source_model(grid, meters):
    notes = tuple(Note(start, start + min(.25, end-start), 60+i, 0, 0,
                       "right", f"source-{i}")
                  for i, (start, end) in enumerate(zip(grid, grid[1:])))
    phrase = Phrase(1, 1, len(grid)-1, 0, grid[-1], notes)
    score = build_lesson_score(
        phrase, boundaries=grid, time_signatures=meters,
        key_signatures=(KeySignature(0, 2), KeySignature(grid[-2], -3)),
        clef_changes=(ClefChange(0, "G", 2, hand="right"),
                      ClefChange(grid[-2], "F", 4, hand="right")))
    return build_score_model(score, boundaries=grid)


@pytest.mark.parametrize("grid,meters,want_gap,want_stride", [
    ((0, 3, 7), ((0, 3, 4), (3, 4, 4)), 3, 10),
    ((0, .5, 3.5, 4.5), ((0, 3, 4), (3.5, 2, 4)), 3, 7.5),
    ((0, 3, 4), ((0, 6, 8), (3, 2, 4)), 3, 7),
    ((0, .5, 6.5), ((0, 1, 8), (.5, 12, 8)), .5, 7),
])
def test_upcoming_full_meter_defines_gap_despite_pickup_and_short_ending(
        grid, meters, want_gap, want_stride):
    model = source_model(grid, meters)
    assert "practice_timeline" in model
    timeline = model["practice_timeline"]
    gap = timeline["gap"]
    assert timeline["schema"] == "piano-teacher-practice-timeline-v1"
    assert timeline["source_duration_beats"] == grid[-1]
    assert timeline["stride_beats"] == want_stride
    assert (gap["start_beat"], gap["end_beat"], gap["duration_beats"]) == (
        grid[-1], want_stride, want_gap)
    assert gap["meter"] == list(meters[0][1:])
    assert gap["keys"] == {"right": 2, "left": 2}
    assert gap["clefs"]["right"] == {"sign": "G", "line": 2, "octave_change": 0}
    assert gap["kind"] == "measure_rest" and gap["origin"] == "practice"
    assert gap["full_measure"] and gap["note_type"] == "whole" and gap["dots"] == 0
    assert gap["staves"] == ["right", "left"]
    for side in ("left_barline", "right_barline"):
        assert gap[side] == {"style": "regular", "repeat": ""}
    assert gap["events"] == [
        {"id": f"practice:gap:{staff}", "source_id": None, "kind": "rest",
         "staff": staff, "duration_beats": want_gap, "full_measure": True,
         "is_attack": False, "graded": False}
        for staff in ("right", "left")]
    assert len(model["notes"]) == len(grid)-1
    assert all(not event["id"].startswith("practice:")
               for event in model["notation_events"])
    assert json.loads(json.dumps(timeline)) == timeline


def test_descriptor_owns_context_and_does_not_mutate_source():
    from piano_teacher.notation.practice_timeline import practice_timeline_descriptor
    measures = [{"meter": [3, 4], "keys": {"right": 1, "left": 1},
                 "clefs": {"right": {"sign": "G", "line": 2, "octave_change": 0}}}]
    before = deepcopy(measures)
    result = practice_timeline_descriptor(measures, 1, staff_order=("left", "right"))
    assert result["stride_beats"] == 4
    assert result["gap"]["staves"] == ["left", "right"]
    result["gap"]["clefs"]["right"]["line"] = 4
    result["gap"]["meter"][0] = 9
    assert measures == before
