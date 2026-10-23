"""Phase 3 coverage is exhaustive and does not silently skip hard symbols."""
from copy import deepcopy

import pytest

from scripts.audit_phase3_whole_pieces import (
    BUNDLED_MIDI, measure_windows, verify_complete_windows,
)
from scripts import audit_phase3_whole_pieces as audit


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


def test_capture_failure_retains_each_original_construct_as_unverified(tmp_path):
    from pathlib import Path
    source=Path(__file__).parent/"fixtures/musical_fidelity/xml_chord_ties.musicxml"
    rows=audit.unverified_window_elements(source,"score.musicxml","both",1,2,tmp_path,"capture failed")
    assert len(rows)>10
    assert len({r["id"] for r in rows})==len(rows)
    assert all(r["status"]=="unverified" for r in rows)
    assert {"pitch","tie","rest","clef","measure"} <= {r["construct"] for r in rows}


def test_failed_midi_capture_preserves_inherent_written_score_limitation(tmp_path):
    rows=audit.unverified_window_elements(tmp_path/"piece.mid","piece.mid","left",1,4,tmp_path,"capture failed")
    sentinel=next(row for row in rows if row["construct"]=="midi_written_transcription")
    assert sentinel["status"]=="unsupported"
    assert "MIDI" in sentinel["reason"]


def test_attack_free_tail_is_captured_with_preceding_measures():
    from types import SimpleNamespace
    piece=SimpleNamespace(bar_boundaries=tuple(range(10)),
                          notes=[SimpleNamespace(start=0),SimpleNamespace(start=4)])
    windows=audit.piece_measure_windows(piece,4)
    assert windows==((1,4),(5,9))
    assert [bar for first,last in windows for bar in range(first,last+1)]==list(range(1,10))


def test_opening_silence_and_empty_middle_windows_are_not_skipped():
    from types import SimpleNamespace
    piece=SimpleNamespace(bar_boundaries=tuple(range(14)),
                          notes=[SimpleNamespace(start=5),SimpleNamespace(start=12)])
    windows=audit.piece_measure_windows(piece,4)
    assert windows==((1,12),(13,13))
    assert [bar for first,last in windows for bar in range(first,last+1)]==list(range(1,14))
