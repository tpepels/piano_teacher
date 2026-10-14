"""Tempo-driven Phase 1 transport, pause/resume and MIDI timestamp tests."""
from pathlib import Path
from types import SimpleNamespace
import pytest
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.server import PracticeEngine
from piano_teacher import server


def piece():
    notes = (Note(0, 1, 60, 0, 0, 'right'), Note(2, 3, 64, 0, 0, 'right'))
    return Piece('Transport exercise', 100, notes, (Phrase(1, 1, 2, 0, 8, notes),))


@pytest.fixture
def harness(tmp_path, monkeypatch):
    t = [100.0]
    monkeypatch.setattr(server.time, 'monotonic', lambda: t[0])
    e = PracticeEngine(tmp_path, enable_midi=False)
    e.plan = LearningPlan(piece())
    try:
        yield e, t
    finally:
        e.db.close()


def test_signed_beat_is_continuous_at_downbeat(harness):
    e, t = harness
    e.start()
    assert e.state()['clock_beat'] == pytest.approx(-8)
    assert e.state()['transport_id'] == 1
    t[0] = 106
    assert e.state()['clock_beat'] == pytest.approx(-4)
    t[0] = 112
    assert e.state()['phase'] == 'playing'
    assert e.state()['clock_beat'] == pytest.approx(0)
    t[0] = 114.25
    assert e.state()['clock_beat'] == pytest.approx(1.5)
    assert e.state()['beat'] == pytest.approx(1.5)


def test_pause_during_count_in_freezes_clock(harness):
    e, t = harness
    e.start()
    t[0] = 102.25
    e.control('pause')
    assert e.state()['phase'] == 'paused'
    assert e.state()['clock_beat'] == pytest.approx(-6.5)
    t[0] = 192.25
    assert e.state()['clock_beat'] == pytest.approx(-6.5)
    e.control('resume')
    assert e.state()['phase'] == 'count_in'
    t[0] = 202
    assert e.state()['phase'] == 'playing'
    assert e.state()['clock_beat'] == pytest.approx(0)


def test_pause_preserves_recorded_midi_timing(harness):
    e, t = harness
    e.start()
    t[0] = 113.5
    e._receive(SimpleNamespace(type='note_on', note=60, velocity=90))
    assert len(e.recorder.presses) == 1
    e.control('pause')
    t[0] = 707.5
    e._receive(SimpleNamespace(type='note_on', note=70, velocity=90))
    assert len(e.recorder.presses) == 1
    assert e.state()['clock_beat'] == pytest.approx(1)
    e.control('resume')
    t[0] = 708.25
    e._receive(SimpleNamespace(type='note_off', note=60, velocity=0))
    assert e.state()['clock_beat'] == pytest.approx(1.5)
    assert e.recorder.presses[0].onset == pytest.approx(1.5)
    assert e.recorder.presses[0].release == pytest.approx(2.25)


def test_restart_clears_attempt_but_not_mastery(harness):
    e, t = harness
    e.start()
    t[0] = 113.5
    e._receive(SimpleNamespace(type='note_on', note=60, velocity=90))
    ident = e.transport_id
    e.control('restart')
    assert e.state()['phase'] == 'count_in'
    assert e.state()['clock_beat'] == pytest.approx(-8)
    assert e.transport_id == ident + 1
    assert e.state()['midi_notes'] == 0
    assert e.plan.index == 0 and not e.plan.mastered


def test_invalid_pause_and_resume_rejected(harness):
    e, _ = harness
    with pytest.raises(ValueError, match='Cannot pause'):
        e.control('pause')
    with pytest.raises(ValueError, match='Cannot resume'):
        e.control('resume')
    e.start()
    with pytest.raises(ValueError, match='Cannot resume'):
        e.control('resume')
    e.control('pause')
    with pytest.raises(ValueError, match='Cannot pause'):
        e.control('pause')


def test_paused_preview_never_advances_learning(harness):
    e, t = harness
    e.start()
    t[0] = 113
    e.control('pause')
    t[0] = 407
    assert e.state()['phase'] == 'paused'
    e.control('resume')
    t[0] = 426.3
    state = e.state()
    assert state['phase'] == 'ready' and not state['running']
    assert state['mastered'] == 0


def test_godot_uses_one_clock_and_freezes_on_pause():
    script = (Path(__file__).resolve().parents[1] / 'godot' / 'main.gd').read_text()
    for source in ['func _transport_beat_now() -> float:',
                   'var beat: float = _transport_beat_now()',
                   'var clock: float = _transport_beat_now()',
                   'not bool(last_state.get("paused", false))',
                   'func _toggle_pause() -> void:',
                   'func _restart_practice() -> void:']:
        assert source in script
