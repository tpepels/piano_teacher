"""Clock tests: count-in and score timing do not wait for MIDI input."""
import pytest
from test_phase1_camera import native_camera_run
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.server import PracticeEngine
from piano_teacher import server


def _piece():
    notes = (Note(0, 0.5, 64, 0, 0, "right"),
             Note(1, 1.5, 67, 0, 0, "right"))
    phrase = Phrase(1, 1, 2, 0, 8, notes)
    return Piece("Clocked practice", 100, notes, (phrase,))


def test_timeline_moves_at_exact_tempo_even_without_piano(tmp_path, monkeypatch):
    t = [100.0]
    monkeypatch.setattr(server.time, "monotonic", lambda: t[0])
    engine = PracticeEngine(tmp_path, enable_midi=True)
    engine.plan = LearningPlan(_piece())
    try:
        engine.start()
        assert engine.state()["preview_only"] is True
        assert engine.state()["phase"] == "count_in"
        assert engine.state()["beat"] == 0
        assert engine.state()["count_in_beats"] == pytest.approx(2.5)
        # Godot and MIDI assessment receive the same absolute monotonic
        # run_at. No state response is permitted to re-zero the display.
        state = engine.state()
        assert state["visual_run_at_ms"] == pytest.approx(engine.run_at * 1000.0)
        downbeat = engine.run_at
        assert downbeat-t[0] <= 4.0
        t[0] = downbeat - .1
        assert engine.state()["phase"] == "count_in"
        assert engine.state()["beat"] == 0
        t[0] = downbeat
        assert engine.state()["phase"] == "playing"
        assert engine.state()["beat"] == 0
        t[0] = downbeat + .75
        assert engine.state()["beat"] == pytest.approx(0.5)
        t[0] = downbeat + 3.0
        assert engine.state()["beat"] == pytest.approx(2.0)
        assert engine.state()["midi_notes"] == 0
        t[0] = downbeat + 11.8
        assert engine.state()["phase"] == "playing"
        t[0] = downbeat + 12.3
        done = engine.state()
        assert done["phase"] == "preview_gap"
        assert done["running"] is False and done["preview_only"]
        assert done["visual_scroll_speed"] > 0
        assert "repeating after one empty measure" in done["feedback"]
        assert done["mastered"] == 0 and done["take_result"] is None
        assert engine.plan.index == 0
        revision = engine.score_revision
        t[0] = engine.next_at + .01
        repeated = engine.state()
        assert repeated["phase"] == "playing" and repeated["preview_only"]
        assert repeated["count_in_beats"] == 0
        assert repeated["revision"] == revision
        assert repeated["mastered"] == 0
        assert engine.plan.index == 0
    finally:
        engine.db.close()


def test_tempo_control_changes_count_in_and_cursor_speed(tmp_path, monkeypatch):
    t = [25.0]
    monkeypatch.setattr(server.time, "monotonic", lambda: t[0])
    engine = PracticeEngine(tmp_path, enable_midi=True)
    engine.plan = LearningPlan(_piece())
    try:
        engine.control("tempo", bpm=80)
        engine.start()
        assert engine.state()["bpm"] == 80
        assert engine.run_at == pytest.approx(28.0)
        t[0] = 29.5
        assert engine.state()["beat"] == pytest.approx(2.0)
        assert engine.state()["phase"] == "playing"
    finally:
        engine.db.close()


def test_frontend_has_time_driven_native_beam(native_camera_run):
    report, _ = native_camera_run
    assert report["clock_matched"] and report["resume_advanced"]
    assert report["pause_frozen"]


def test_frontend_prevents_start_before_native_notation(tmp_path):
    from test_native_production import test_native_production_readiness_and_failure_gate

    test_native_production_readiness_and_failure_gate(tmp_path, "default")
