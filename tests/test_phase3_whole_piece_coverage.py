"""Phase 3 coverage is exhaustive and does not silently skip hard symbols."""
from copy import deepcopy

import pytest

from scripts.audit_phase3_whole_pieces import (
    BUNDLED_MIDI, measure_windows, verify_complete_windows,
)


def _witness(first: int, last: int) -> dict:
    return {
        "first_bar":first,
        "last_bar":last,
        "whole_window_coverage":{
            "measure_count":last-first+1,
            "sampled_measures":last-first+1,
            "source_noteheads":4*(last-first+1),
            "unique_rendered_noteheads":4*(last-first+1),
            "source_rests":2*(last-first+1),
            "unique_rendered_rests":2*(last-first+1),
            "screenshot_count":6*(last-first+1),
            "missing_notes":[],"missing_rests":[],
            "missing_measure_starts":[],"unexpected_notes":[],
            "unexpected_rests":[],
        },
    }


@pytest.mark.parametrize("bars,chunk",[(1,1),(2,4),(9,4),(12,5),(19,1)])
def test_each_measure_appears_exactly_once(bars,chunk):
    windows=measure_windows(bars,chunk)
    assert [n for a,b in windows for n in range(a,b+1)]==list(range(1,bars+1))
    result=verify_complete_windows(bars,[_witness(a,b) for a,b in windows])
    assert result["passed"], result["errors"]
    assert result["measures_witnessed"]==bars


@pytest.mark.parametrize("key,wrong",[
    ("missing_notes",["n-3"]),
    ("missing_rests",["r-3"]),
    ("missing_measure_starts",[3]),
    ("unexpected_notes",["rogue"]),
    ("unexpected_rests",["rogue-rest"]),
])
def test_symbol_omissions_and_extra_ink_are_failures(key,wrong):
    rows=[_witness(1,4),_witness(5,7)]
    rows[1]["whole_window_coverage"][key]=wrong
    assert not verify_complete_windows(7,rows)["passed"]


def test_missing_window_does_not_pass():
    result=verify_complete_windows(9,[_witness(1,4),_witness(9,9)])
    assert not result["passed"]
    assert result["missing_measures"]==[5,6,7,8]


def test_duplicate_measure_window_does_not_pass():
    result=verify_complete_windows(7,[
        _witness(1,4),_witness(4,7)])
    assert not result["passed"]
    assert result["duplicated_measures"]==[4]


def test_no_screenshot_witness_is_a_failure():
    result=verify_complete_windows(1,[{
        "first_bar":1,"last_bar":1,"whole_window_coverage":None}])
    assert not result["passed"]


def test_incorrect_per_window_measure_count_is_a_failure():
    row=_witness(1,4)
    row["whole_window_coverage"]["sampled_measures"]=3
    assert not verify_complete_windows(4,[row])["passed"]


def test_corpus_is_pinned_to_all_seven_bundled_midi_files():
    assert len(BUNDLED_MIDI)==len(set(BUNDLED_MIDI))==7
    assert all(name.endswith(".midi") for name in BUNDLED_MIDI)


@pytest.mark.parametrize("bars,window",[(0,4),(4,0),(-1,4)])
def test_invalid_window_request_fails_closed(bars,window):
    with pytest.raises(ValueError):
        measure_windows(bars,window)


@pytest.mark.parametrize("field,value",[
    ("unique_rendered_noteheads",0),
    ("unique_rendered_rests",0),
    ("screenshot_count",0),
    ("measure_count",3),
])
def test_incomplete_counts_cannot_hide_behind_empty_error_lists(field,value):
    row=_witness(1,4)
    row["whole_window_coverage"][field]=value
    assert not verify_complete_windows(4,[row])["passed"]
