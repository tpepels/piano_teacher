"""Listen and Perform use real source notes without Practice progression."""
import wave
import time

import mido
import pytest

from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from test_instructional_recovery import lesson, send, play, boundary, finish_take, after_break


def wait_audio(e):
    worker = e._demo_thread
    worker.join(10)
    assert not worker.is_alive(), 'Audio synthesis did not finish'
    return e.state()


def acknowledge(e, *, audio_first=False):
    state = wait_audio(e) if e.state().get('demo') else e.state()
    e.geometry()
    demo = state.get('demo')
    if audio_first and demo:
        e.control('demo_ready', token=demo['token'], revision=state['revision'])
    e.control('score_ready', revision=state['revision'])
    if not audio_first and demo:
        e.control('demo_ready', token=demo['token'], revision=state['revision'])
    return e.state()


@pytest.mark.parametrize('bpm', (30, 40, 80, 120))
def test_listen_is_audible_exact_full_variant_and_cannot_grade_midi(lesson, bpm):
    e, now, grid = lesson(bpm, chords=True)
    e.control('learn')
    acknowledge(e)
    assert e.state()['required_notes'] == 8
    identity = e.plan.identity
    e.control('listen')
    loading = e.state()
    assert loading['mode'] == 'listen' and loading['phase'] == 'loading'
    assert loading['required_notes'] == 16  # Full skeleton, even after short Learn.
    demo = loading['demo']
    assert demo['stage_key'] == identity and len(demo['source_ids']) == 16
    assert len(set(demo['source_ids'])) == 16
    assert demo['duration_seconds'] == pytest.approx(16*60/bpm)
    assert not demo['ready'] and e.recorder is None
    available = wait_audio(e)
    assert available['demo']['audio_available'] and available['demo']['url']
    audio = e.demo_audio(demo['token'])
    with wave.open(str(audio), 'rb') as wav:
        assert wav.getnchannels() == 1 and wav.getsampwidth() == 2
        assert wav.getnframes()/wav.getframerate() == pytest.approx(16*60/bpm)
        assert any(wav.readframes(min(wav.getnframes(), wav.getframerate())))
    e.control('score_ready', revision=loading['revision'])
    assert e.state()['phase'] == 'loading'
    now[0] += 3
    e.control('demo_ready', token=demo['token'], revision=loading['revision'])
    listening = e.state()
    assert listening['phase'] == 'playing' and listening['running']
    assert listening['clock_beat'] == pytest.approx(0)
    assert listening['count_in_beats'] == 0 and listening['demo']['ready']
    assert e.recorder is None and not e.auto and not listening['preview_only']
    send(e, now, now[0]+.1, 90)
    send(e, now, now[0]+.2, 90, False)
    assert e.recorder is None and e.pending_result is None
    assert e.state()['demo']['token'] == demo['token']
    now[0] = e.run_at+demo['duration_seconds']+.01
    done = e.state()
    assert done['mode'] == 'listen' and done['phase'] == 'ready'
    assert e.plan.streak == 0 and not e.plan.mastered and e.plan.bpm == bpm
    assert 'Practice' in done['next_action']


@pytest.mark.parametrize('audio_first', (False, True))
def test_listen_both_readiness_gates_freeze_during_pause_and_stale_acks_never_start(lesson, audio_first):
    e, now, _ = lesson()
    e.control('listen')
    first = e.state()
    e.control('listen')
    current = wait_audio(e)
    e.control('score_ready', revision=first['revision'])
    e.control('demo_ready', token=first['demo']['token'], revision=first['revision'])
    assert e.state()['phase'] == 'loading'
    e.control('pause')
    if audio_first:
        e.control('demo_ready', token=current['demo']['token'], revision=current['revision'])
        e.control('score_ready', revision=current['revision'])
    else:
        e.control('score_ready', revision=current['revision'])
        e.control('demo_ready', token=current['demo']['token'], revision=current['revision'])
    now[0] += 100
    assert e.state()['phase'] == 'paused' and not e.state()['running']
    e.control('resume')
    assert e.state()['phase'] == 'playing' and e.state()['clock_beat'] == pytest.approx(0)
    now[0] += .75
    beat = e.state()['clock_beat']
    e.control('pause')
    now[0] += 90
    assert e.state()['clock_beat'] == pytest.approx(beat)
    e.control('resume')
    assert e.state()['clock_beat'] == pytest.approx(beat)
    e.control('stop')
    e.control('score_ready', revision=current['revision'])
    e.control('demo_ready', token=current['demo']['token'], revision=current['revision'])
    assert e.state()['phase'] == 'ready' and not e.state()['running']
    with pytest.raises(ValueError):
        e.demo_audio(current['demo']['token'])


def test_tempo_change_abandons_listen_token_and_retains_selected_mode(lesson):
    e, _, _ = lesson()
    e.control('listen')
    old = e.state()
    e.control('tempo', bpm=60)
    e.control('score_ready', revision=old['revision'])
    e.control('demo_ready', token=old['demo']['token'], revision=old['revision'])
    state = e.state()
    assert state['mode'] == 'listen' and state['phase'] == 'ready'
    assert state['bpm'] == state['target_bpm'] == 60 and not state['running']
    assert state['demo'] is None
    e.control('start')
    fresh = e.state()
    assert fresh['mode'] == 'listen' and fresh['phase'] == 'loading'
    assert fresh['demo']['duration_seconds'] == 16
    with pytest.raises(ValueError):
        e.demo_audio(old['demo']['token'])


@pytest.mark.parametrize('bpm', (30, 40, 80, 120))
@pytest.mark.parametrize('mixed', (False, True))
def test_perform_all_misses_keeps_full_clock_and_finishes_in_review_without_practice_credit(lesson, bpm, mixed):
    e, now, grid = lesson(bpm, mixed)
    identity = e.plan.identity
    e.control('perform')
    loading = e.state()
    assert loading['phase'] == 'loading' and loading['mode'] == 'perform'
    e.control('score_ready', revision=loading['revision']-1)
    assert e.state()['phase'] == 'loading'
    playing = acknowledge(e)
    assert playing['phase'] == 'count_in' and playing['bpm'] == bpm
    assert boundary(e, now, grid[2])['phase'] == 'playing'
    assert e.state()['bpm'] == bpm and e.pending_rewind is None
    now[0] = e.run_at+(grid[-1]-.1)*60/bpm
    assert e.state()['phase'] == 'playing'
    now[0] = e.run_at+grid[-1]*60/bpm+.22
    review = e.state()
    assert review['phase'] == 'performance_complete' and not review['running']
    assert review['performance_summary']['total'] == grid[-1]
    assert review['performance_summary']['correct'] == 0
    assert review['performance_summary']['accuracy_percent'] == 0
    assert review['performance_summary']['missed_pitches'] == [60, 62, 64, 65]
    assert review['performance_summary']['early'] == review['performance_summary']['late'] == 0
    weakest = review['performance_summary']['weakest_bars'][0]
    # Equal counts prefer the earlier source chunk; mixed 3/4→4/4 prefers 8-note chunk.
    assert weakest == ({'first_bar': 3, 'last_bar': 4, 'start_beat': 6, 'end_beat': 14, 'errors': 8}
                       if mixed else {'first_bar': 1, 'last_bar': 2, 'start_beat': 0, 'end_beat': 8, 'errors': 8})
    assert e.pending_result is None and not e.auto and not e.plan.mastered
    assert e.plan.identity == identity and e.plan.bpm == bpm and e.plan.streak == 0
    now[0] += 100
    assert e.state()['performance_summary'] == review['performance_summary']
    assert e.state()['phase'] == 'performance_complete'


def test_perform_callback_summary_points_to_later_chunk_then_practice_weak_is_a_partial(lesson):
    e, now, grid = lesson(80)
    e.control('perform')
    acknowledge(e)
    play(e, now, before=8, jitter=True)
    # One early note and one wrong pitch, then six misses.
    send(e, now, e.run_at+8*60/80-.15, 60)
    send(e, now, e.run_at+8.5*60/80-.15, 60, False)
    send(e, now, e.run_at+9*60/80, 90)
    send(e, now, e.run_at+9.5*60/80, 90, False)
    now[0] = e.run_at+16*60/80+.22
    review = e.state()
    summary = review['performance_summary']
    assert summary['correct'] == 8 and summary['total'] == 16
    assert summary['accuracy_percent'] == 50 and summary['early'] == 1
    assert summary['weakest_bars'][0]['first_bar'] == 3
    assert any(mark['status'] == 'wrong' for mark in review['feedback_marks'])
    e.control('practice_weak')
    waiting = e.state()
    assert waiting['mode'] == 'practice' and waiting['phase'] == 'ready'
    assert waiting['retry_range']['start_beat'] == 8
    assert e.review_end_beat == 16
    e.start()  # A deliberate retry waits for the pianist, not score-ready.
    started = e.state()
    assert started['phase'] == 'count_in' and started['play_from_beat'] == 8
    assert started['bpm'] == started['target_bpm'] == 80
    now[0] = e.run_at + (16-8)*60/80 + .21
    reviewed = e.state()
    assert reviewed['phase'] == 'review' and not reviewed['running']
    assert reviewed['performance_summary']['missed'] > 0
    assert not e.plan.mastered and e.plan.streak == 0
    assert e.next_at == 0  # Never silently continue beyond a selected retry.


def test_clean_perform_does_not_fill_practice_clean_streak_or_master_stage(lesson):
    e, now, _ = lesson()
    for _ in range(2):
        finish_take(e, now, 16)
        after_break(e, now)
    assert e.plan.streak == 2
    e.control('perform')
    acknowledge(e)
    state = finish_take(e, now, 16)
    assert state['phase'] == 'performance_complete'
    assert state['performance_summary']['accuracy_percent'] == 100
    assert e.plan.streak == 2 and not e.plan.mastered
    with pytest.raises(ValueError):
        e.control('practice_weak')


def test_whole_piece_perform_uses_all_original_events_and_held_ending(lesson):
    e, now, _ = lesson()
    notes = (Note(2, 3, 60, 0, 0, 'right'), Note(2, 3, 64, 0, 0, 'right'),
             Note(10, 18, 48, 1, 0, 'left'), Note(12, 13, 67, 0, 0, 'right'))
    piece = Piece('Imported complete piece', 80, notes,
                  (Phrase(1, 1, 2, 0, 8, notes[:2]), Phrase(2, 3, 4, 8, 16, notes[2:])),
                  bar_boundaries=(0, 4, 8, 12, 16, 20), time_signatures=((0, 4, 4),))
    e.plan = LearningPlan(piece)
    e.plan.set_bpm(80)
    e.control('perform', scope='whole')
    state = e.state()
    assert state['hand'] == 'both' and state['lesson_level'] == 'original'
    assert e.plan.active_phrase.notes == notes
    assert state['duration_beats'] == 20 and state['required_notes'] == 4
    acknowledge(e)
    now[0] = e.run_at+19*60/80
    assert e.state()['phase'] == 'playing'
    now[0] = e.run_at+20*60/80+.22
    assert e.state()['phase'] == 'performance_complete'


def test_listen_render_does_not_block_controls_and_late_result_cannot_revive_stopped_demo(lesson):
    import threading
    import time
    from piano_teacher.demo import DemoAudioCache
    e, _, _ = lesson()
    entered, release = threading.Event(), threading.Event()
    real_cache = DemoAudioCache(e._data_dir / 'test-slow-audio', sample_rate=8000)
    class SlowCache:
        def render(self, variant, bpm):
            entered.set()
            release.wait(2)
            return real_cache.render(variant, bpm)
    e._demo_cache = SlowCache()
    started = time.perf_counter()
    try:
        e.control('listen')
        assert time.perf_counter()-started < .5
        assert entered.wait(.5)
        loading = e.state()
        assert loading['phase'] == 'loading'
        assert loading['demo']['url'] == '' and not loading['demo']['audio_available']
        e.control('score_ready', revision=loading['revision'])
        e.control('demo_ready', revision=loading['revision'], token=loading['demo']['token'])
        assert not e.state()['running']
        e.control('pause')
        assert e.state()['phase'] == 'paused'
        e.control('stop')
        assert e.state()['phase'] == 'ready'
    finally:
        release.set()
        worker = getattr(e, '_demo_thread', None)
        if worker:
            worker.join(5)
    assert e.state()['demo'] is None and not e.state()['running']


def test_performance_summary_counts_missed_events_separately_from_unique_pitches(lesson):
    e, now, _ = lesson()
    e.control('perform')
    acknowledge(e)
    now[0] = e.run_at+16*60/80+.22
    summary = e.state()['performance_summary']
    assert summary['missed'] == 16 and summary['wrong'] == 0
    assert len(summary['missed_pitches']) == 4


def test_old_render_cannot_replace_a_new_tempo_demo(lesson):
    import threading
    from piano_teacher.demo import DemoAudioCache
    e, _, _ = lesson()
    entered, release = threading.Event(), threading.Event()
    real_cache = DemoAudioCache(e._data_dir / 'test-replaced-audio', sample_rate=8000)
    class SlowFirstCache:
        def render(self, variant, bpm):
            if bpm == 80:
                entered.set()
                release.wait(3)
            return real_cache.render(variant, bpm)
    e._demo_cache = SlowFirstCache()
    e.control('listen')
    first_worker = e._demo_thread
    assert entered.wait(.5)
    try:
        e.control('tempo', bpm=60)
        e.control('listen')
        current = wait_audio(e)['demo']
        assert current['duration_seconds'] == 16 and current['audio_available']
    finally:
        release.set()
        first_worker.join(5)
    assert not first_worker.is_alive()
    assert e.state()['demo'] == current


def test_failed_background_render_exposes_honest_error_and_cannot_be_acknowledged(lesson):
    e, _, _ = lesson()
    class FailedCache:
        def render(self, variant, bpm):
            raise OSError('Controlled unavailable audio cache')
    e._demo_cache = FailedCache()
    e.control('listen')
    state = wait_audio(e)
    assert state['phase'] == 'ready' and not state['running']
    assert 'could not' in state['feedback'] and state['demo']['error']
    assert not state['demo']['audio_available'] and not state['demo']['url']
    e.control('score_ready', revision=state['revision'])
    e.control('demo_ready', token=state['demo']['token'], revision=state['revision'])
    assert e.state()['phase'] == 'ready' and not e.state()['running']
    assert e.recorder is None and not e.plan.mastered


def test_real_demo_http_route_returns_pcm_and_rejects_abandoned_tokens(lesson):
    import threading
    import urllib.request
    import urllib.error
    from http.server import ThreadingHTTPServer
    from piano_teacher.server import Handler
    e, _, _ = lesson(120)
    e.control('listen')
    state = wait_audio(e)
    handler = type('DemoHandler', (Handler,), {'engine': e})
    http = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        url = f'http://127.0.0.1:{http.server_port}'+state['demo']['url']
        with urllib.request.urlopen(url, timeout=3) as reply:
            body = reply.read()
            assert reply.status == 200 and reply.headers['Content-Type'] == 'audio/wav'
            assert int(reply.headers['Content-Length']) == len(body)
            assert body[:4] == b'RIFF' and body[8:12] == b'WAVE'
        e.control('stop')
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(url, timeout=3)
        assert error.value.code == 400
    finally:
        http.shutdown()
        http.server_close()
        thread.join(3)


def test_listen_without_piano_remains_audible_and_never_grades(lesson):
    e, now, _ = lesson(120, connected=False)
    e.control('listen')
    state = acknowledge(e)
    assert state['phase'] == 'playing' and state['demo']['audio_available']
    send(e, now, now[0]+.1, 60)
    assert e.recorder is None and e.pending_result is None and not e.plan.mastered
    now[0] = e.run_at+state['demo']['duration_seconds']+.01
    assert e.state()['phase'] == 'ready'


def test_perform_loading_ack_and_clock_freeze_with_pause_then_stop_discards_review(lesson):
    e, now, _ = lesson()
    e.control('perform')
    revision = e.state()['revision']
    e.control('pause')
    e.control('score_ready', revision=revision)
    now[0] += 30
    assert e.state()['phase'] == 'paused' and not e.state()['running']
    e.control('resume')
    assert e.state()['phase'] == 'count_in' and e.state()['mode'] == 'perform'
    now[0] = e.run_at+1
    e.control('pause')
    beat = e.state()['clock_beat']
    now[0] += 50
    e.control('resume')
    assert e.state()['clock_beat'] == beat
    e.control('stop')
    now[0] += 100
    e.control('score_ready', revision=revision)
    stopped = e.state()
    assert stopped['phase'] == 'ready' and stopped['performance_summary'] is None
    assert stopped['mode'] == 'perform' and not e.plan.mastered


def test_duplicate_ready_ack_cannot_replay_a_completed_listen(lesson):
    e, now, _ = lesson(120)
    e.control('listen')
    playing = acknowledge(e)
    token, revision = playing['demo']['token'], playing['revision']
    transport = playing['transport_id']
    now[0] = e.run_at+playing['demo']['duration_seconds']+.01
    assert e.state()['phase'] == 'ready'
    for _ in range(2):
        e.control('demo_ready', token=token, revision=revision)
        e.control('score_ready', revision=revision)
        complete = e.state()
        assert complete['phase'] == 'ready' and not complete['running']
        assert complete['transport_id'] == transport
    e.control('stop')
    e.control('demo_ready', token=token, revision=revision)
    e.control('score_ready', revision=revision)
    assert e.state()['phase'] == 'ready' and not e.state()['running']
    assert e.recorder is None and e.pending_result is None and not e.plan.mastered


def test_return_from_listen_waits_for_pianist_instead_of_auto_start(lesson):
    engine, now, _ = lesson(80)
    engine.control("listen")
    listen = wait_audio(engine)
    assert listen["mode"] == "listen"
    engine.control("practice", wait_for_player=True)
    ready = engine.state()
    assert ready["mode"] == "practice"
    assert ready["phase"] == "ready"
    assert not ready["running"]
    assert engine.awaiting_score_revision is None
    # Even a late score-ready acknowledgement must not start the passage.
    engine.geometry()
    engine.control("score_ready", revision=ready["revision"])
    assert engine.state()["phase"] == "ready"
    assert not engine.state()["running"]
    engine.start()
    assert engine.state()["phase"] == "count_in"
