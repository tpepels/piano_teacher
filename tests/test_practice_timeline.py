"""Derived practice silence must never change the canonical source events."""
from copy import deepcopy
import json
from pathlib import Path

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


@pytest.mark.parametrize("grid,meters,want_gap,want_stride,want_meter", [
    ((0, 3, 7), ((0, 3, 4), (3, 4, 4)), 3, 10, [3, 4]),
    ((0, .5, 3.5, 4.5), ((0, 3, 4), (3.5, 2, 4)), 3, 7.5, [3, 4]),
    ((0, 3, 4), ((0, 6, 8), (3, 2, 4)), 3, 7, [6, 8]),
    ((0, .5, 6.5), ((0, 1, 8), (.5, 12, 8)), 6, 12.5, [12, 8]),
    ((0, .5, 4.5), ((0, 1, 8), (.5, 4, 4)), 4, 8.5, [4, 4]),
    ((0, .5, 1), ((0, 1, 8),), .5, 1.5, [1, 8]),
    ((0, .5, 1, 5), ((0, 1, 8), (1, 4, 4)), .5, 5.5, [1, 8]),
    ((0, .5, 3.5), ((0, 6, 8),), 3, 6.5, [6, 8]),
    ((0, .5, 6.5), ((0, 12, 8),), 6, 12.5, [12, 8]),
])
def test_upcoming_full_meter_defines_gap_despite_pickup_and_short_ending(
        grid, meters, want_gap, want_stride, want_meter):
    model = source_model(grid, meters)
    assert "practice_timeline" in model
    timeline = model["practice_timeline"]
    gap = timeline["gap"]
    assert timeline["schema"] == "piano-teacher-practice-timeline-v1"
    assert timeline["source_duration_beats"] == grid[-1]
    assert timeline["stride_beats"] == want_stride
    assert (gap["start_beat"], gap["end_beat"], gap["duration_beats"]) == (
        grid[-1], want_stride, want_gap)
    assert gap["meter"] == want_meter
    assert gap["source_meter"] == list(meters[0][1:])
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
    measures = [{"start_beat": 0, "end_beat": 1,
                 "meter": [3, 4], "keys": {"right": 1, "left": 1},
                 "clefs": {"right": {"sign": "G", "line": 2, "octave_change": 0}}}]
    before = deepcopy(measures)
    result = practice_timeline_descriptor(measures, 1, staff_order=("left", "right"))
    assert result["stride_beats"] == 4
    assert result["gap"]["staves"] == ["left", "right"]
    result["gap"]["clefs"]["right"]["line"] = 4
    result["gap"]["meter"][0] = 9
    assert measures == before


@pytest.mark.parametrize("spans,duration", [
    pytest.param([(1, 2)], 2, id="nonzero-origin"),
    pytest.param([(-1, 1)], 1, id="negative-origin"),
    pytest.param([(0, 0)], 1, id="zero-length"),
    pytest.param([(0, 2), (2, 1)], 1, id="reversed-measure"),
    pytest.param([(0, 1), (2, 3)], 3, id="gap"),
    pytest.param([(0, 2), (1, 3)], 3, id="overlap"),
    pytest.param([(0, 1), (0, 1)], 1, id="duplicate"),
    pytest.param([(0, 2)], 1, id="source-longer-than-duration"),
    pytest.param([(0, 1)], 2, id="source-shorter-than-duration"),
    pytest.param([(0, 1), (1.00000001, 2)], 2, id="small-gap"),
    pytest.param([(0, float("nan"))], 1, id="nan-end"),
    pytest.param([(0, float("inf"))], 1, id="infinite-end"),
    pytest.param([(float("nan"), 1)], 1, id="nan-start"),
    pytest.param([(float("-inf"), 1)], 1, id="infinite-start"),
    pytest.param([(0, 1), (float("nan"), 2)], 2, id="nan-interior-start"),
])
def test_timeline_rejects_invalid_source_grid_without_rewriting_it(spans, duration):
    from piano_teacher.notation.practice_timeline import practice_timeline_descriptor
    measures = [{"start_beat": start, "end_beat": end,
                 "meter": [4, 4], "keys": {}, "clefs": {}}
                for start, end in spans]
    before = deepcopy(measures)
    with pytest.raises(ValueError):
        practice_timeline_descriptor(measures, duration)
    assert measures == before


@pytest.mark.parametrize("missing", ("start_beat", "end_beat"))
def test_timeline_requires_explicit_source_boundaries(missing):
    from piano_teacher.notation.practice_timeline import practice_timeline_descriptor
    measure = {"start_beat": 0, "end_beat": 1,
               "meter": [4, 4], "keys": {}, "clefs": {}}
    del measure[missing]
    with pytest.raises(ValueError):
        practice_timeline_descriptor([measure], 1)


@pytest.mark.parametrize("duration", (0, -1, float("nan"), float("inf")))
def test_timeline_rejects_nonpositive_or_nonfinite_source_duration(duration):
    from piano_teacher.notation.practice_timeline import practice_timeline_descriptor
    measure = {"start_beat": 0, "end_beat": 1,
               "meter": [4, 4], "keys": {}, "clefs": {}}
    with pytest.raises(ValueError):
        practice_timeline_descriptor([measure], duration)


@pytest.mark.parametrize("meter", [
    (0, 4), (-1, 4), (4, 0), (4, -1),
    (float("nan"), 4), (4, float("nan")),
    (float("inf"), 4), (4, float("inf")),
    (1e308, 1), (5e-324, 1e308),
])
@pytest.mark.parametrize("following", (False, True))
def test_preparation_rejects_invalid_meter_or_duration(meter, following):
    from piano_teacher.notation.practice_timeline import preparation_measure_descriptor
    context = {"start_beat": 0, "end_beat": .5,
               "meter": [1, 8] if following else meter, "keys": {}, "clefs": {}}
    upcoming = {"start_beat": .5, "end_beat": 4.5, "meter": meter}
    with pytest.raises(ValueError):
        preparation_measure_descriptor(
            context, 0, following_measure=upcoming if following else None)


@pytest.mark.parametrize("start,meter", [
    (float("nan"), [4, 4]), (float("inf"), [4, 4]),
    (1e308, [3e307, 1]), (1e20, [4, 4]),
])
def test_preparation_requires_finite_positive_span(start, meter):
    from piano_teacher.notation.practice_timeline import preparation_measure_descriptor
    with pytest.raises(ValueError):
        preparation_measure_descriptor({"meter": meter, "keys": {}, "clefs": {}}, start)


@pytest.mark.parametrize("hand", ("right", "left"))
def test_real_peace_piece_opening_prepares_four_beats_without_rewriting_pickup(hand):
    from piano_teacher.importing.pieces import import_piece
    from piano_teacher.learning import LearningPlan
    from piano_teacher.music import source_note_id
    from piano_teacher.notation.lesson import infer_piece_clefs
    path = Path(__file__).resolve().parents[1] / "midi/Peace_Piece_-_Bill_Evans_(Piano_Solo).midi"
    piece, _ = import_piece(path)
    plan = LearningPlan(piece)
    plan.set_hand(hand)
    phrase = plan.active_phrase
    score = build_lesson_score(
        phrase, boundaries=piece.bar_boundaries, time_signatures=piece.time_signatures,
        key_signatures=piece.key_signatures, clef_changes=piece.clef_changes,
        default_clefs=infer_piece_clefs(piece.notes))
    model = build_score_model(score, boundaries=piece.bar_boundaries, hand=hand)
    assert piece.time_signatures[:2] == ((0, 1, 8), (.5, 4, 4))
    assert [(m["start_beat"], m["end_beat"], m["meter"]) for m in model["measures"]] == [
        (0, .5, [1, 8]), (.5, 4.5, [4, 4])]
    gap = model["practice_timeline"]["gap"]
    assert gap["duration_beats"] == 4
    assert gap["meter"] == [4, 4] and gap["source_meter"] == [1, 8]
    assert (gap["start_beat"], gap["end_beat"]) == (4.5, 8.5)
    assert model["practice_timeline"]["stride_beats"] == 8.5
    assert {n["id"]: (n["midi_pitch"], n["hand"], n["onset_beats"])
            for n in model["notes"]} == {
        source_note_id(n, i): (n.pitch, n.hand, round(n.start-phrase.start, 8))
        for i, n in enumerate(phrase.notes)}
    assert all(event["source_id"] is None and not event["graded"] for event in gap["events"])


def test_preparation_measure_can_use_immediate_following_meter_but_keeps_source_context():
    from piano_teacher.notation.practice_timeline import preparation_measure_descriptor
    measures = source_model((0, .5, 4.5), ((0, 1, 8), (.5, 4, 4)))["measures"]
    before = deepcopy(measures)
    gap = preparation_measure_descriptor(measures[0], -4, following_measure=measures[1])
    assert (gap["start_beat"], gap["end_beat"], gap["duration_beats"]) == (-4, 0, 4)
    assert gap["source_meter"] == [1, 8] and gap["meter"] == [4, 4]
    assert gap["keys"] == {"right": 2, "left": 2}
    assert gap["clefs"]["right"]["sign"] == "G"
    assert measures == before
