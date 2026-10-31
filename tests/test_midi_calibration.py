"""Three median-calibrated MIDI rounds with audible 4-beat preparation."""
import pytest

from piano_teacher.midi_calibration import MidiTapCalibration
from piano_teacher.library import ScoreLibrary
from piano_teacher.server import PracticeEngine


def three_rounds(session, offsets=(.08,.09,.085), count=8):
    for round_index, offset in enumerate(offsets):
        first = session.start_at + (
            round_index * session.round_beats + session.count_in) * session.period
        for n in range(count):
            # Sparse deterministic human timing variation remains below 8ms.
            assert session.observe(first + n * session.period + offset
                                   + (n % 3 - 1)*.006)
    return session.snapshot(session.start_at + session.rounds *
                            session.round_beats * session.period + .01)


def test_count_in_before_each_of_three_tap_rounds_and_median():
    session = MidiTapCalibration()
    session.start(100.0)
    assert session.snapshot(100.0)["phase"] == "ready"
    assert session.snapshot(session.start_at)["phase"] == "count_in"
    assert session.snapshot(session.start_at)["countdown"] == 4
    assert not session.observe(session.start_at + session.period)  # countdown
    assert session.snapshot(session.start_at+4*session.period)["phase"] == "tap"
    assert session.snapshot(session.start_at+4*session.period)["tap_number"] == 1
    assert session.snapshot(session.start_at+12*session.period)["round"] == 2
    assert session.snapshot(session.start_at+12*session.period)["phase"] == "count_in"
    assert session.snapshot(session.start_at+24*session.period)["round"] == 3
    done = three_rounds(session, offsets=(.12,.13,.125))
    assert not done["active"] and done["phase"] == "finished"
    assert done["result"]["samples"] == 24
    assert len(done["result"]["rounds"]) == 3
    assert done["result"]["reliable"]
    assert 119 <= done["result"]["estimate_ms"] <= 132


def test_inconsistent_round_medians_rejected():
    session = MidiTapCalibration()
    session.start(10.0)
    done = three_rounds(session, (.02, .10, .17))
    assert not done["result"]["reliable"]
    assert "disagree" in done["result"]["error"]


def test_implausibly_large_or_negative_delay_rejected():
    for offset in (.255, -.075):
        session = MidiTapCalibration()
        session.start(10.0)
        result = three_rounds(session, (offset, offset, offset))["result"]
        assert not result["reliable"]


def test_missing_round_cannot_be_applied():
    session = MidiTapCalibration()
    session.start(0.0)
    done = three_rounds(session, count=5)
    assert not done["result"]["reliable"]
    assert "at least six" in done["result"]["error"]


def test_calibration_applies_only_after_three_reliable_rounds(tmp_path):
    app = PracticeEngine(tmp_path, enable_midi=False)
    try:
        with pytest.raises(ValueError, match="Connect"):
            app.control("calibration_start")
        app.midi.port = object()
        app.control("calibration_start")
        cal = app.midi_calibration
        for round_index in range(2):
            first = cal.start_at + (round_index*cal.round_beats+cal.count_in)*cal.period
            for n in range(8):
                assert cal.observe(first+n*cal.period+.08)
        with pytest.raises(ValueError, match="Finish"):
            app.control("calibration_apply")
        for n in range(8):
            first = cal.start_at + (2*cal.round_beats+cal.count_in)*cal.period
            assert cal.observe(first+n*cal.period+.08)
        assert app.library.settings["midi_offset_ms"] == 0
        cal.snapshot(cal.start_at+36*cal.period+.1)
        app.control("calibration_apply")
        assert app.library.settings["midi_offset_ms"] == 80
        assert ScoreLibrary(tmp_path/"config").settings["midi_offset_ms"] == 80
        app.control("calibration_reset")
        assert app.library.settings["midi_offset_ms"] == 0
    finally:
        app.db.close()
