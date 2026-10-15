"""Clock tests: count-in and score timing do not wait for MIDI input."""
from pathlib import Path
import pytest
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
        assert done["phase"] == "ready"
        assert done["running"] is False
        assert "Timing preview complete" in done["feedback"]
        assert done["mastered"] == 0
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


def test_frontend_has_time_driven_beam_and_prevents_start_before_notation():
    gd = (Path(__file__).resolve().parents[1] / "godot" / "main.gd").read_text()
    assert 'func _transport_beat_now() -> float:' in gd
    assert 'float(last_state.get("clock_beat", 0.0))' in gd
    assert 'beat += elapsed * float(last_state.get("bpm", 60.0)) / 60.0' in gd
    assert 'score_overlay.transport_active = active' in gd
    assert 'var minimum_x: float = viewport.x * 0.08 - focus_right * displayed_width' in gd
    assert 'target_x = viewport.x * 0.42 - note_x * displayed_width' in gd
    assert 'score_content.position.lerp(target, blend)' in gd
    assert 'start_button.disabled = false' in gd
    assert 'Preparing sheet music - wait for the notes' in gd
