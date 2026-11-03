"""Continuous five-round MIDI calibration, robust outliers and persistence."""
import pytest

from piano_teacher.midi_calibration import MidiTapCalibration
from piano_teacher.library import ScoreLibrary
from piano_teacher.server import PracticeEngine


def five_rounds(session, offsets=(.08, .085, .09, .08, .085),
                count=8, errors=None):
    errors = errors or {}
    for round_index, offset in enumerate(offsets):
        first = session.start_at + (
            session.count_in + round_index * session.ticks) * session.period
        for n in range(count):
            assert session.observe(first + n * session.period + offset
                                   + (n % 3 - 1) * .006
                                   + errors.get((round_index, n), 0.0))
    return session.snapshot(
        session.start_at + session.total_beats * session.period + .01)


def test_one_count_in_followed_by_five_uninterrupted_rounds():
    session = MidiTapCalibration()
    session.start(100.0)
    assert session.rounds == 5
    assert session.snapshot(100.0)["phase"] == "ready"
    assert session.snapshot(session.start_at)["phase"] == "count_in"
    assert session.snapshot(session.start_at)["countdown"] == 4
    assert not session.observe(session.start_at + session.period)
    for index in range(5):
        at = session.start_at + (session.count_in + index * 8) * session.period
        snapshot = session.snapshot(at)
        assert snapshot["phase"] == "tap"  # rounds 2-5 have no count-in
        assert snapshot["round"] == index + 1
        assert snapshot["tap_number"] == 1
    done = five_rounds(session, offsets=(.12, .13, .125, .12, .13))
    assert not done["active"] and done["phase"] == "finished"
    assert done["result"]["samples"] == 40
    assert len(done["result"]["rounds"]) == 5
    assert done["result"]["reliable"]
    assert done["result"]["used_rounds"] == 5
    assert 119 <= done["result"]["estimate_ms"] <= 132
    assert done["progress"] == 1.0


def test_single_fumbled_note_is_trimmed_without_corrupting_delay():
    session = MidiTapCalibration()
    session.start(10.0)
    result = five_rounds(session, (.08,) * 5, errors={(2, 5): .16})["result"]
    assert result["reliable"]
    assert result["discarded_taps"] == 1
    assert result["rounds"][2]["discarded_taps"] == 1
    assert result["rounds"][2]["accepted_samples"] == 7
    assert result["estimate_ms"] == pytest.approx(80, abs=3)


def test_one_outlying_round_does_not_discard_the_whole_session():
    session = MidiTapCalibration()
    session.start(10.0)
    result = five_rounds(session, (.08, .08, .18, .08, .08))["result"]
    assert result["reliable"]
    assert result["used_rounds"] == 4
    assert result["discarded_rounds"] == 1
    assert result["rounds"][2]["reliable"]
    assert not result["rounds"][2]["included"]
    assert result["estimate_ms"] == pytest.approx(80, abs=3)


def test_two_round_outliers_are_not_silently_accepted():
    session = MidiTapCalibration()
    session.start(10.0)
    result = five_rounds(session, (.08, .08, .18, .19, .08))["result"]
    assert not result["reliable"]
    assert "disagree" in result["error"]


def test_inconsistent_round_medians_rejected():
    session = MidiTapCalibration()
    session.start(10.0)
    result = five_rounds(session, (.02, .10, .17, .08, .12))["result"]
    assert not result["reliable"]
    assert "disagree" in result["error"]


def test_implausibly_large_or_negative_delay_rejected():
    for offset in (.255, -.075):
        session = MidiTapCalibration()
        session.start(10.0)
        result = five_rounds(session, (offset,) * 5)["result"]
        assert not result["reliable"]
        assert "safe" in result["error"]


def test_less_than_four_reliable_rounds_cannot_be_applied():
    session = MidiTapCalibration()
    session.start(0.0)
    done = five_rounds(session, count=5)
    assert not done["result"]["reliable"]
    assert "at least four" in done["result"]["error"]


def test_one_missing_round_can_be_excluded_but_two_cannot():
    for missing in ((1,), (1, 3)):
        session = MidiTapCalibration()
        session.start(100.0)
        for round_index in range(session.rounds):
            if round_index in missing:
                continue
            first = session.start_at + (
                session.count_in + round_index * session.ticks) * session.period
            for n in range(session.ticks):
                assert session.observe(first + n * session.period + .08)
        result = session.snapshot(
            session.start_at + session.total_beats * session.period)["result"]
        assert result["reliable"] == (len(missing) == 1)
        if len(missing) == 1:
            assert result["used_rounds"] == 4
            assert result["discarded_rounds"] == 1


def test_double_notes_and_count_in_notes_are_not_collected():
    session = MidiTapCalibration()
    session.start(100)
    assert not session.observe(session.start_at + session.period + .08)
    first = session.start_at + session.count_in * session.period + .08
    assert session.observe(first)
    assert not session.observe(first + .005)
    assert session.snapshot(first)["round_samples"] == [1, 0, 0, 0, 0]


def test_calibration_applies_only_after_five_rounds(tmp_path):
    app = PracticeEngine(tmp_path, enable_midi=False)
    try:
        with pytest.raises(ValueError, match="Connect"):
            app.control("calibration_start")
        app.midi.port = object()
        app.control("calibration_start")
        cal = app.midi_calibration
        for round_index in range(4):
            first = cal.start_at + (
                cal.count_in + round_index * cal.ticks) * cal.period
            for n in range(8):
                assert cal.observe(first + n * cal.period + .08)
        with pytest.raises(ValueError, match="Finish"):
            app.control("calibration_apply")
        first = cal.start_at + (cal.count_in + 4 * cal.ticks) * cal.period
        for n in range(8):
            assert cal.observe(first + n * cal.period + .08)
        assert app.library.settings["midi_offset_ms"] == 0
        cal.snapshot(cal.start_at + cal.total_beats * cal.period + .1)
        app.control("calibration_apply")
        assert app.library.settings["midi_offset_ms"] == 80
        assert ScoreLibrary(tmp_path / "config").settings["midi_offset_ms"] == 80
        app.control("calibration_reset")
        assert app.library.settings["midi_offset_ms"] == 0
    finally:
        app.db.close()


def test_start_replaces_old_measurements_and_cancel_preserves_saved_offset():
    session = MidiTapCalibration()
    session.start(10.0)
    assert five_rounds(session)["result"]["reliable"]
    session.start(100.0)
    assert session.result is None
    assert session.snapshot(100)["samples"] == 0
    session.cancel()
    assert session.result is None


def test_calibration_epoch_is_backend_sampled_not_a_poll_midpoint(tmp_path):
    session = MidiTapCalibration()
    session.start(100.0)
    captured = session.snapshot(100.25)
    assert captured["start_at_ms"] == pytest.approx(101000.0)
    assert captured["sampled_at_ms"] == pytest.approx(100250.0)
    assert captured["beat"] == pytest.approx(-1.0)

    engine = PracticeEngine(tmp_path / "fresh", enable_midi=False)
    try:
        state = engine.state()
        assert not state["loaded"]
        assert "clock_sampled_at_ms" in state
        assert state["midi_calibration"]["sampled_at_ms"] == pytest.approx(
            state["clock_sampled_at_ms"], abs=20)
    finally:
        engine.db.close()
