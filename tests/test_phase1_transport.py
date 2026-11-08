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
    e.fingerprint = "phase1-transport-fixture"
    try:
        yield e, t
    finally:
        e.db.close()


def test_signed_beat_is_continuous_at_downbeat(harness):
    e, t = harness
    # Owner decision 2026-11-08: the count-in is always a full bar, here
    # 4 beats = 6 s at 40 BPM (the former 4 s cap gave 2.5 beats).
    e.start()
    assert e.state()['clock_beat'] == pytest.approx(-4.0)
    assert e.state()['transport_id'] == 1
    t[0] = 101.5
    assert e.state()['clock_beat'] == pytest.approx(-3.0)
    t[0] = 106.0
    assert e.state()['phase'] == 'playing'
    assert e.state()['clock_beat'] == pytest.approx(0)
    t[0] = 108.25
    assert e.state()['clock_beat'] == pytest.approx(1.5)
    assert e.state()['beat'] == pytest.approx(1.5)


def test_clock_snapshot_publishes_its_authoritative_sample_time(harness):
    e, t = harness
    assert e.state().get('clock_sampled_at_ms') == pytest.approx(t[0] * 1000)
    e.start()
    t[0] += 1.25
    snapshot = e.state()
    assert snapshot.get('clock_sampled_at_ms') == pytest.approx(t[0] * 1000)
    assert snapshot['clock_beat'] == pytest.approx((t[0] - e.visual_transport.run_at) * e.plan.bpm / 60)


def test_pause_during_count_in_freezes_clock(harness):
    e, t = harness
    e.start()
    t[0] = 101.5
    e.control('pause')
    assert e.state()['phase'] == 'paused'
    # Full-bar count-in (owner decision 2026-11-08): 4 beats at 40 BPM.
    assert e.state()['clock_beat'] == pytest.approx(-3.0)
    t[0] = 191.5
    assert e.state()['clock_beat'] == pytest.approx(-3.0)
    e.control('resume')
    assert e.state()['phase'] == 'count_in'
    t[0] = 196.0
    assert e.state()['phase'] == 'playing'
    assert e.state()['clock_beat'] == pytest.approx(0)


def test_pause_preserves_recorded_midi_timing(harness):
    e, t = harness
    e.start()
    # One beat after the full-bar count-in (6 s at 40 BPM, owner 2026-11-08).
    t[0] = 107.5
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


@pytest.mark.parametrize('mode', ('practice', 'perform'))
def test_restart_clears_attempt_but_not_mastery(harness, mode):
    e, t = harness
    e.plan.mastered[e.plan.identity] = 100
    mastery = dict(e.plan.mastered)
    e.start(mode=mode)
    initial = e.state()
    # Full-bar count-in at any tempo (owner decision 2026-11-08).
    assert initial['phase'] == 'count_in' and initial['count_in_beats'] == 4
    assert initial['clock_beat'] == -4 and e.plan.bpm == 40
    t[0] = 107.5
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
        assert restarted['count_in_beats'] == 4 and restarted['clock_beat'] == -4
        assert restarted['practice_preparation'] is None
        assert e.transport_id == ident+1 and e.visual_transport.run_at == restart_at+6.0
        t[0] = e.visual_transport.run_at-.01
        assert e.state()['phase'] == 'count_in'
        t[0] = e.visual_transport.run_at
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
        assert e.visual_transport.next_at == deadline
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
        assert e.visual_transport.next_at == deadline
        t[0] = deadline
        playing = e.state()
        assert playing['phase'] == 'playing' and playing['clock_beat'] == 0
        assert playing['count_in_beats'] == 0 and playing['visual_scroll_beat'] == 0
        assert playing['practice_preparation']['phase'] == 'complete'
        assert e.visual_transport.run_at == deadline and e.transport_id == ident+1
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
    t[0] = e.visual_transport.next_at + .01
    repeated = e.state()
    assert repeated['phase'] == 'playing' and repeated['preview_only']
    assert repeated['revision'] == revision
    assert repeated['count_in_beats'] == 0
    assert repeated['mastered'] == 0 and repeated['streak'] == 0
    assert e.plan.identity == stage


def test_godot_uses_single_transport_sample_for_music_and_metronome():
    root = Path(__file__).resolve().parents[1] / 'godot'
    main = (root / 'main.gd').read_text()
    click_owner = (root / 'metronome_frame_coordinator.gd').read_text()
    assert 'visual_transport_clock.accept(parsed,last_state_tick,received_ms)' in main
    assert 'var beat: float = _transport_beat_at(ticks)' in main
    assert '_update_count_in(beat,ticks)' in main
    assert 'func _toggle_pause() -> void:' in main
    assert 'func _restart_practice() -> void:' in main
    cue_timeline = (root / 'countin_cue_timeline.gd').read_text()
    assert 'if paused:' in click_owner
    assert '_cues.hold(token,beat)' in click_owner
    # The engine's one count-in bar windows every cue (owner, 2026-11-08).
    assert '_dispatch_cue(token,beat,bar,false,count_in_beats)' in click_owner
    assert 'var tick := floori(beat + .00001)' in cue_timeline
    assert '"accent":posmod(tick,meter) == 0' in cue_timeline


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
    # The whole 3/4 bar, never shortened (owner decision 2026-11-08).
    assert e.state()['count_in_beats'] == pytest.approx(3)
    # The current metronome coordinator consumes the same authored source
    # meter in both normal and preparation phases; Main only supplies beat.
    root = Path(__file__).resolve().parents[1] / 'godot'
    clicks = (root / 'metronome_frame_coordinator.gd').read_text()
    main = (root / 'main.gd').read_text()
    assert 'state.get("count_in_bar_beats",4)' in clicks
    assert 'CueTimeline.new()' in clicks
    assert '"accent":posmod(tick,meter) == 0' in (
        root / 'countin_cue_timeline.gd').read_text()
    assert 'practice_view.stage.count_in.present(beat,bar,true,paused,count_in_beats)' in clicks
    assert 'metronome_frame.update(last_state,last_state_tick,sampled_beat,now_ms)' in main


def test_explicit_renderer_reading_lead_keeps_midi_on_authoritative_resume_clock(harness):
    e, t = harness
    e.start()
    t[0] = e.visual_transport.run_at + 1.25
    before = e.state()["clock_beat"]
    e.control("pause")
    t[0] += 2.0
    e.control("resume", presentation_lead_seconds=7.5)
    resumed = e.state()
    assert resumed["phase"] == "count_in"
    assert resumed["transport_id"] == 1
    # The renderer's reserved lead is the deadline. It is longer than the
    # one full count-in bar (4 beats = 6 s at 40 BPM; owner decisions of
    # 2026-11-08: one count-in bar, always a whole bar), so it applies as is.
    assert e._resume_grading_after == pytest.approx(t[0]+7.5)
    assert resumed["count_in_beats"] == pytest.approx(4.0)
    t[0] += 7.0
    assert e.state()["phase"] == "count_in"
    assert e.recorder is not None and len(e.recorder.presses) == 0
    t[0] += 0.5
    assert e.state()["phase"] == "playing"
    assert e.state()["clock_beat"] == pytest.approx(before)
    assert e.state()["transport_id"] == 1


def test_requested_future_lead_delays_first_source_without_shifting_its_notes(harness):
    e, t = harness
    e.start(presentation_lead_seconds=8.0)
    assert e.visual_transport.run_at == pytest.approx(108.0)
    assert e.state()["phase"] == "count_in"
    t[0] = 108.0
    assert e.state()["clock_beat"] == pytest.approx(0.0)
    assert e.state()["phase"] == "playing"


def test_worker_resume_command_reserves_future_note_deadline(harness):
    import json
    from piano_teacher.inprocess import EngineCommands

    engine, now = harness
    engine.start()
    now[0] = engine.visual_transport.run_at + 1.5
    engine.control("pause")
    now[0] += 2.0
    clock_before = engine.state()["clock_beat"]
    status, payload = EngineCommands(engine=engine).request(
        "practice.command",
        json.dumps({"action":"resume","presentation_lead_seconds":7.0}))
    assert status == 0, payload
    published = json.loads(payload)
    assert published["phase"] == "count_in"
    assert published["transport_id"] == 1
    assert engine._resume_grading_after == pytest.approx(now[0]+7.0)
    now[0] += 7.0
    assert engine.state()["clock_beat"] == pytest.approx(clock_before)
    assert engine.state()["phase"] == "playing"



def test_single_future_stage_schedule_respects_offscreen_source_reading_time():
    from piano_teacher.application.transport_commands import scheduled_offscreen_start
    assert scheduled_offscreen_start(100.0, 14.0, 31.0) == pytest.approx(
        100.0 + 14.0*60.0/31.0)
    assert scheduled_offscreen_start(105.0, 0.0, 40.0) == 105.0
    for lead in (float("nan"), float("inf"), -1.0, 65.0):
        with pytest.raises(ValueError, match="future notation"):
            scheduled_offscreen_start(105.0, lead, 40.0)


def test_future_stage_acknowledgement_records_verified_offscreen_lead():
    from threading import RLock
    from types import SimpleNamespace
    selection = SimpleNamespace(stage_key="stage-v2", revision=2)
    class Prepared:
        def __init__(self):
            self.lock = RLock()
            self.future_score = SimpleNamespace(ready=lambda _selection: True)
            self.pending_result = None
            self._future_stage_ready = None
            self._future_stage_lead_beats = 0.0
        def _next_stage_selection(self, *, offset=1):
            return (selection, 2) if offset == 1 else None
    fake = Prepared()
    result = PracticeEngine.acknowledge_preloaded_stage(
        fake, stage_key="stage-v2", revision=2,
        presentation_lead_beats=14.0)
    assert result["accepted"]
    assert fake._future_stage_ready == ("stage-v2",2)
    assert fake._future_stage_lead_beats == 14.0
    with pytest.raises(ValueError, match="future notation reading lead"):
        PracticeEngine.acknowledge_preloaded_stage(
            fake, stage_key="stage-v2", revision=2,
            presentation_lead_beats=float("nan"))
    assert fake._future_stage_lead_beats == 14.0
