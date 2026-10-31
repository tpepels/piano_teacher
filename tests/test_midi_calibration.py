"""Bounded tap-calibration contracts; no actual Bluetooth latency inferred."""
import pytest

from piano_teacher.midi_calibration import MidiTapCalibration
from piano_teacher.library import ScoreLibrary
from piano_teacher.server import PracticeEngine


def test_consistent_metronome_taps_estimate_offset_and_jitter():
    session = MidiTapCalibration()
    session.start(100.0)
    assert session.snapshot(100.0)["active"]
    for i in range(8):
        tick = session.start_at + i * session.period
        assert session.observe(tick + .13 + ((i % 3) - 1) * .008)
        assert not session.observe(tick + .14)
    done = session.snapshot(session.start_at + 8 * session.period + .1)
    assert not done["active"]
    assert done["result"]["reliable"]
    assert done["result"]["samples"] == 8
    assert 115 <= done["result"]["estimate_ms"] <= 140
    assert done["result"]["jitter_ms"] <= 10


def test_uncertain_taps_are_never_auto_applied():
    session = MidiTapCalibration()
    session.start(10.0)
    for i, offset in enumerate((.29, -.29, .28, -.28, .27, -.27)):
        assert session.observe(session.start_at+i*session.period+offset)
    result = session.snapshot(session.start_at+8*session.period+.1)["result"]
    assert not result["reliable"]


def test_calibration_does_not_start_without_midi_and_applies_only_on_confirmation(tmp_path):
    app = PracticeEngine(tmp_path, enable_midi=False)
    try:
        with pytest.raises(ValueError, match="Connect"):
            app.control("calibration_start")
        app.midi.port = object()
        app.control("calibration_start")
        cal = app.midi_calibration
        for i in range(8):
            assert cal.observe(cal.start_at+i*cal.period+.08)
        assert app.library.settings["midi_offset_ms"] == 0
        cal.snapshot(cal.start_at+8*cal.period+.1)
        app.control("calibration_apply")
        assert app.library.settings["midi_offset_ms"] == 80
        assert ScoreLibrary(tmp_path).settings["midi_offset_ms"] == 80
        app.control("calibration_reset")
        assert app.library.settings["midi_offset_ms"] == 0
    finally:
        app.db.close()
