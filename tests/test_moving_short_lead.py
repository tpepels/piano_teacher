"""Tempo-capped count-in is short even when beginning at very slow BPM."""
import pytest
from piano_teacher.lesson_timing import lead_in_beats
from test_phase1_camera import native_camera_run


@pytest.mark.parametrize("bar,bpm,expected", [
    (4, 100, 4),
    (3, 100, 3),
    (4, 40, 2.5),
    (3, 40, 2.5),
    (4, 20, 1),
    (3, 12, 0.5),
    (3, 120, 3),
])
def test_lead_in_is_at_most_one_measure_and_about_four_seconds(bar, bpm, expected):
    lead = lead_in_beats(bar, bpm)
    assert lead == expected
    assert lead <= bar
    assert lead * 60 / bpm <= 4.01


def test_invalid_count_in_inputs_fail():
    for args in [(0,40), (4,0), (-2,120)]:
        with pytest.raises(ValueError):
            lead_in_beats(*args)


def test_godot_scrolling_is_unconditional_during_transport(native_camera_run):
    report, _ = native_camera_run
    assert report["short_passage"], "Probe must exercise a score narrower than the viewport"
    lead = [s for s in report["samples"] if s["label"] == "lead"]
    playing = [s for s in report["samples"] if s["label"] == "playing"]
    assert len(lead) >= 2 and playing
    samples = lead + playing
    for first, second in zip(samples, samples[1:]):
        a = {h["id"]: h["x"] for h in first["heads"]}
        b = {h["id"]: h["x"] for h in second["heads"]}
        common = a.keys() & b.keys()
        assert common
        advance = (second["clock"] - first["clock"]) * first["density"]
        assert advance > 0
        for ident in common:
            assert a[ident] - b[ident] == pytest.approx(advance, abs=.002)
