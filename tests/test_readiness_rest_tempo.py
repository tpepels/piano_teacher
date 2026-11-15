"""Rest duration comes from actual source tempo, not a nominal BPM guess."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


READINESS = Path(__file__).resolve().parent / "readiness"
if str(READINESS) not in sys.path:
    sys.path.insert(0, str(READINESS))
from invariants import _take_duration_ms


def test_half_rate_coda_note_is_not_mistaken_for_an_extra_rest_bar():
    nominal = {"len": 2, "bpm": 24, "pf": 0}
    shaped = dict(nominal, tempo_segments=[
        {"start_beat": 0, "end_beat": 2, "bpm": 12},
    ])
    assert _take_duration_ms(nominal) == pytest.approx(5000)
    assert _take_duration_ms(shaped) == pytest.approx(10000)
    # First beat at t=0, next graded beat at t=20s. Two bars of actual
    # silence (10s), not three bars invented by nominal source timing.
    next_graded_ms = 20000
    bar_ms = 2 * 60000 / 24
    assert (next_graded_ms-_take_duration_ms(nominal))/bar_ms == pytest.approx(3)
    assert (next_graded_ms-_take_duration_ms(shaped))/bar_ms == pytest.approx(2)


def test_piecewise_tempo_map_and_partial_retries_use_exact_graded_seconds():
    piecewise = [
        {"start_beat": 0, "end_beat": 1, "bpm": 24},
        {"start_beat": 1, "end_beat": 2, "bpm": 12},
    ]
    assert _take_duration_ms({
        "len": 2, "bpm": 24, "tempo_segments": piecewise,
    }) == pytest.approx(7500)
    assert _take_duration_ms({
        "len": 1, "pf": 1, "bpm": 24,
        "tempo_segments": piecewise,
    }) == pytest.approx(5000)
    assert _take_duration_ms({
        "len": 1, "pf": 1, "bpm": 24,
        "tempo_segments": [{"start_beat": 0, "end_beat": 1, "bpm": 12}],
    }) == pytest.approx(5000)


def test_malformed_tempo_evidence_fails_instead_of_silently_forging_rest():
    with pytest.raises(ValueError):
        _take_duration_ms({"len": 2, "bpm": 24,
                           "tempo_segments": [
                               {"start_beat": 0, "end_beat": 1, "bpm": 12},
                           ]})
    with pytest.raises(ValueError):
        _take_duration_ms({"len": 2, "bpm": 24,
                           "tempo_segments": [
                               {"start_beat": 1, "end_beat": 2, "bpm": 12},
                           ]})
