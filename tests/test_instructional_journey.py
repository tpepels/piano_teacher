"""One MIDI learner prepares, recovers, earns mastery and reviews real music."""
import os
import shutil

import pytest
import mido

from piano_teacher import server
from piano_teacher.learning import LearningPlan
from piano_teacher.learner_state import guided_units
from piano_teacher.music import load_midi
from scripts.smoke_instructional_godot import make_fixture, run


def expected_route(piece):
    """Inspect the real default route without starting a server or transport."""
    plan = LearningPlan(piece)
    return {
        "source_grid": piece.bar_boundaries,
        "stages": [(step.kind, step.first_bar, step.last_bar, step.level,
                    step.required_notes) for step in plan.lesson_steps],
        "guided_units": [(unit["start_beat"], unit["end_beat"], unit["required_notes"])
                         for unit in guided_units(plan.active_variant, piece.bar_boundaries)],
        "partial_attacks": sum(note.start >= piece.bar_boundaries[1]
                               for note in plan.active_variant.notes),
    }


def test_instructional_fixture_keeps_partial_retry_inside_default_two_measure_route(tmp_path):
    source = tmp_path / "lesson.mid"
    make_fixture(source)
    # A second-measure retry has five misses: the five-error recovery
    # threshold stays intact, and that partial cannot earn full-stage mastery.
    assert expected_route(load_midi(source)) == {
        "source_grid": (0, 8, 16),
        "stages": [("learn", 1, 2, "skeleton", 8),
                   ("learn", 1, 2, "original", 16)],
        "guided_units": [(0, 16, 8)],
        "partial_attacks": 5,
    }


def test_source_measure_retry_still_reaches_five_errors_and_clean_partial_cannot_master(tmp_path, monkeypatch):
    source = tmp_path/'lesson.mid'
    make_fixture(source)
    now = [100.0]
    monkeypatch.setattr(server.time, 'monotonic', lambda: now[0])
    engine = server.PracticeEngine(tmp_path/'data', enable_midi=False)

    def ready():
        state = engine.state()
        engine.geometry()
        engine.control('score_ready', revision=state['revision'])
        return engine.state()

    def send(pitch, down):
        engine._receive(mido.Message('note_on' if down else 'note_off',
                                    note=pitch, velocity=80 if down else 0))

    try:
        engine.load(str(source))
        engine.midi.port = object()
        engine.control('tempo', bpm=240)
        engine.control('practice')
        assert ready()['phase'] == 'count_in'
        stage = engine.plan.identity
        engine.control('pause')
        engine.control('seek', bar=2)
        assert ready()['play_from_beat'] == 8
        for bpm, guided in ((216, False), (194, True)):
            now[0] = engine.run_at+8*60/engine.plan.bpm+.03
            failed = engine.state()
            assert failed['phase'] == 'recovering' and failed['bpm'] == bpm
            assert failed['guided_recovery'] == guided
            assert failed['retry_range'] == {
                'first_bar': 2, 'last_bar': 2, 'start_beat': 8, 'end_beat': 16}
            now[0] = engine.next_at+.01
            engine.state()
        learned = ready()
        assert learned['phase'] == 'guided_wait'
        assert learned['first_bar'] == learned['last_bar'] == 2
        while engine.state()['phase'] == 'guided_wait':
            for note in engine.state()['teaching']['expected_notes']:
                now[0] += .02
                send(note['pitch'], True)
                send(note['pitch'], False)
        assert engine.state()['phase'] == 'guided_complete'
        engine.control('practice')
        counted = ready()
        assert counted['phase'] == 'count_in' and counted['play_from_beat'] == 8
        events = sorted((at, note.pitch, down)
                        for note in engine.plan.active_phrase.notes if note.start >= 8
                        for at, down in ((note.start, True), (note.end, False)))
        for beat, pitch, down in events:
            now[0] = engine.run_at+(beat-8)*60/engine.plan.bpm+.02
            send(pitch, down)
            engine.state()
        now[0] = engine.run_at+8*60/engine.plan.bpm+.23
        partial = engine.state()
        summary = partial['performance_summary']
        assert summary['correct'] == summary['total'] == 5
        assert summary['missed'] == summary['extra_notes'] == 0
        assert partial['phase'] == 'recovering' and engine.pending_rewind == 0
        assert engine.pending_result is None and engine.plan.identity == stage
        assert not engine.plan.mastered and engine.plan.streak == 0
    finally:
        engine.db.close()


def test_real_student_prepares_recovers_masters_listens_performs_and_revisits(tmp_path, monkeypatch):
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        pytest.skip("Rendered instructional journey requires a graphical desktop")
    if not (shutil.which("godot") or shutil.which("godot4")):
        pytest.skip("Godot unavailable")
    from piano_teacher import sample_piano
    monkeypatch.setattr(sample_piano, "find_soundfont", lambda: None)
    result = run(tmp_path,finish_modes=True)
    assert result["failures"] == []
    assert result["renderer"] != "headless"
    assert result["full_clean_tempos"] == [194,207,223,240,240,240]
    first, second = [frame for frame in result["frames"] if "errors-score-moving-" in frame["frame"]]
    assert first["note_id"] == second["note_id"]
    assert second["note_x"] < first["note_x"]-8
    assert abs(second["line_x"]-first["line_x"]) < 1
    earned = next(frame for frame in result["frames"] if frame["frame"] == "28-next-original-variant.png")
    assert earned["mastered"] == 1 and earned["mode"] == "learn"
    assert result["earned_variant"]["source_notes"] == 16
    assert result["finished_modes"] and result["revisited_trouble"]
    assert result["performance_summary"]["total"] == result["performance_summary"]["missed"] == 16
    example = next(frame for frame in result["frames"] if frame["frame"] == "29-earned-original-listen.png")
    assert example["audio_playing"] and example["pcm_bytes"] > 10000
    assert result["frames"][-1]["mastered"] == 1
    assert len(result["frames"]) >= 25
