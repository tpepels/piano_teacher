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
    assert e.state()['clock_beat'] == pytest.approx(-2.5)
    assert e.state()['transport_id'] == 1
    t[0] = 101.5
    assert e.state()['clock_beat'] == pytest.approx(-1.5)
    t[0] = 103.75
    assert e.state()['phase'] == 'playing'
    assert e.state()['clock_beat'] == pytest.approx(0)
    t[0] = 106
    assert e.state()['clock_beat'] == pytest.approx(1.5)
    assert e.state()['beat'] == pytest.approx(1.5)


def test_clock_snapshot_publishes_its_authoritative_sample_time(harness):
    e, t = harness
    assert e.state().get('clock_sampled_at_ms') == pytest.approx(t[0] * 1000)
    e.start()
    t[0] += 1.25
    snapshot = e.state()
    assert snapshot.get('clock_sampled_at_ms') == pytest.approx(t[0] * 1000)
    assert snapshot['clock_beat'] == pytest.approx((t[0] - e.run_at) * e.plan.bpm / 60)


def test_pause_during_count_in_freezes_clock(harness):
    e, t = harness
    e.start()
    t[0] = 101.5
    e.control('pause')
    assert e.state()['phase'] == 'paused'
    assert e.state()['clock_beat'] == pytest.approx(-1.5)
    t[0] = 191.5
    assert e.state()['clock_beat'] == pytest.approx(-1.5)
    e.control('resume')
    assert e.state()['phase'] == 'count_in'
    t[0] = 193.75
    assert e.state()['phase'] == 'playing'
    assert e.state()['clock_beat'] == pytest.approx(0)


def test_pause_preserves_recorded_midi_timing(harness):
    e, t = harness
    e.start()
    t[0] = 105.25
    e._receive(SimpleNamespace(type='note_on', note=60, velocity=90))
    assert len(e.recorder.presses) == 1
    e.control('pause')
    t[0] = 705.25
    e._receive(SimpleNamespace(type='note_on', note=70, velocity=90))
    assert len(e.recorder.presses) == 1
    assert e.state()['clock_beat'] == pytest.approx(1)
    e.control('resume')
    t[0] = 706.0
    e._receive(SimpleNamespace(type='note_off', note=60, velocity=0))
    assert e.state()['clock_beat'] == pytest.approx(1.5)
    assert e.recorder.presses[0].onset == pytest.approx(1.5)
    assert e.recorder.presses[0].release == pytest.approx(2.25)


@pytest.mark.parametrize('mode', ('practice', 'perform'))
def test_restart_clears_attempt_but_not_mastery(harness, mode):
    e, t = harness
    e.plan.mastered[e.plan.identity] = 100
    mastery = dict(e.plan.mastered)
    e.start(mode=mode)
    initial = e.state()
    assert initial['phase'] == 'count_in' and initial['count_in_beats'] == 2.5
    assert initial['clock_beat'] == -2.5 and e.plan.bpm == 40
    t[0] = 105.25
    e._receive(SimpleNamespace(type='note_on', note=60, velocity=90))
    assert len(e.recorder.presses) == 1
    ident = e.transport_id
    revision = e.score_revision
    restart_at = t[0]
    e.control('restart')
    restarted = e.state()
    assert restarted['midi_notes'] == 0 and restarted['revision'] == revision
    assert e.plan.index == 0 and e.plan.mastered == mastery
    if mode == 'perform':
        # An uninterrupted performance gets a fresh count-in; continuous
        # practice's reverse/preparation lifecycle must not leak into it.
        assert restarted['phase'] == 'count_in'
        assert restarted['count_in_beats'] == 2.5 and restarted['clock_beat'] == -2.5
        assert restarted['practice_preparation'] is None
        assert e.transport_id == ident+1 and e.run_at == restart_at+3.75
        t[0] = e.run_at-.01
        assert e.state()['phase'] == 'count_in'
        t[0] = e.run_at
        playing = e.state()
        assert playing['phase'] == 'playing' and playing['clock_beat'] == 0
    else:
        # The old attempt is discarded immediately. Reverse from source
        # beat 1 to the preceding empty 4/4 measure at beat -4, then read
        # that complete measure at 40 BPM before replaying source beat 0.
        reverse_end = restart_at+e.feedback_seconds
        deadline = reverse_end+4*60/40
        assert restarted['phase'] == 'recovering' and not restarted['running']
        assert restarted['count_in_beats'] == 0 and restarted['clock_beat'] == 0
        assert restarted['practice_preparation']['phase'] == 'reverse'
        measure = restarted['practice_preparation']['measure']
        assert (measure['start_beat'], measure['end_beat'], measure['duration_beats']) == (-4, 0, 4)
        assert restarted['visual_scroll_beat'] == 1
        assert restarted['visual_target_beat'] == -4
        assert restarted['visual_scroll_speed'] == -5/e.feedback_seconds
        assert e.transport_id == ident and e.recorder is None
        assert e.next_at == deadline
        t[0] = restart_at+e.feedback_seconds/2
        reversing = e.state()
        assert reversing['practice_preparation']['phase'] == 'reverse'
        assert reversing['visual_scroll_beat'] == -1.5
        t[0] = reverse_end
        preparing = e.state()
        assert preparing['phase'] == 'recovering' and not preparing['running']
        assert preparing['practice_preparation']['phase'] == 'preparing'
        assert preparing['visual_scroll_beat'] == -4
        assert preparing['visual_scroll_speed'] == 40/60
        t[0] = reverse_end+3
        assert e.state()['visual_scroll_beat'] == -2
        t[0] = deadline-.01
        waiting = e.state()
        assert waiting['phase'] == 'recovering' and waiting['midi_notes'] == 0
        assert e.transport_id == ident and e.recorder is None
        assert e.next_at == deadline
        t[0] = deadline
        playing = e.state()
        assert playing['phase'] == 'playing' and playing['clock_beat'] == 0
        assert playing['count_in_beats'] == 0 and playing['visual_scroll_beat'] == 0
        assert playing['practice_preparation']['phase'] == 'complete'
        assert e.run_at == deadline and e.transport_id == ident+1
    assert playing['midi_notes'] == 0 and playing['revision'] == revision
    assert e.recorder is not None and not e.recorder.presses
    assert e.plan.index == 0 and e.plan.mastered == mastery


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
    revision = e.score_revision
    stage = e.plan.identity
    t[0] = 105
    e.control('pause')
    t[0] = 407
    assert e.state()['phase'] == 'paused'
    e.control('resume')
    t[0] = 420.3
    state = e.state()
    assert state['phase'] == 'preview_gap' and not state['running']
    assert state['preview_only'] and not state['auto']
    assert state['take_result'] is None
    assert state['mastered'] == 0 and state['streak'] == 0
    # The paused duration cannot cause a graded completion or an extra
    # score reload. The preview can still loop after its empty measure.
    t[0] = e.next_at + .01
    repeated = e.state()
    assert repeated['phase'] == 'playing' and repeated['preview_only']
    assert repeated['revision'] == revision
    assert repeated['count_in_beats'] == 0
    assert repeated['mastered'] == 0 and repeated['streak'] == 0
    assert e.plan.identity == stage


def test_godot_uses_one_clock_and_freezes_on_pause():
    script = (Path(__file__).resolve().parents[1] / 'godot' / 'main.gd').read_text()
    for source in ['func _transport_beat_now() -> float:',
                   'var beat: float = _transport_beat_now()',
                   'var clock: float = _transport_beat_now()',
                   'not bool(last_state.get("paused", false))',
                   'func _toggle_pause() -> void:',
                   'func _restart_practice() -> void:']:
        assert source in script


def test_three_four_count_in_retains_meter_for_click_accents(harness):
    e, _ = harness
    # Original length and preparation duration are different at slow speeds.
    notes = (Note(0, 1, 60, 0, 0, 'right'),)
    e.plan = LearningPlan(Piece(
        'Three quarter count', 100, notes,
        (Phrase(1, 1, 2, 0, 6, notes),)
    ))
    e.start()
    assert e.state()['count_in_bar_beats'] == pytest.approx(3)
    assert e.state()['count_in_beats'] < 3
    source = (Path(__file__).resolve().parents[1] / 'godot' / 'main.gd').read_text()
    # Metronome accents still follow the source meter. Numeric labels were
    # deliberately removed in Phase 7.6d; the beat lights use that meter.
    assert 'posmod(tick, bar_beats) == 0' in source
    assert 'last_state.get("count_in_bar_beats", 4)' in source
    assert 'game_count_in.present(beat,' in source
