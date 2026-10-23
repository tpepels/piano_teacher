"""A learner's timestamped MIDI drives instructional recovery and transport."""
import mido
import pytest

from piano_teacher import server
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.server import PracticeEngine


@pytest.fixture
def lesson(tmp_path, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(server.time, 'monotonic', lambda: now[0])
    engines = []

    def create(bpm=80, mixed=False, connected=True, chords=False):
        grid = (0, 3, 6, 10, 14) if mixed else (0, 4, 8, 12, 16)
        notes = tuple(Note(float(i), i + .5, (60, 62, 64, 65)[i % 4]+interval, 0, 0, 'right')
                      for i in range(grid[-1]) for interval in ((0, 4, 7) if chords else (0,)))
        piece = Piece('Imported learner passage', bpm, notes,
                      (Phrase(1, 1, 4, 0, grid[-1], notes),),
                      bar_boundaries=grid,
                      time_signatures=((0, 3, 4), (6, 4, 4)) if mixed else ((0, 4, 4),))
        e = PracticeEngine(tmp_path / str(len(engines)), enable_midi=False)
        engines.append(e)
        e.plan = LearningPlan(piece, consolidate=True)
        e.plan.set_bpm(bpm)
        if connected:
            e.midi_port = object()
            e.midi_device = 'Learner piano'
        e.geometry()
        e.start()
        return e, now, grid

    yield create
    for e in engines:
        e.db.close()


def send(e, now, at, pitch, down=True):
    now[0] = at
    e._receive(mido.Message('note_on' if down else 'note_off', note=pitch,
                           velocity=84 if down else 0))


def play(e, now, *, before=None, jitter=False, omit=()):
    """Perform the displayed source events through the physical-input callback."""
    start, bpm, offset = e.run_at, e.plan.bpm, e.play_from_beat
    notes = [n for n in e.plan.active_phrase.notes if n.start >= offset and n.start not in omit and
             (before is None or n.start < before)]
    events = []
    for i, note in enumerate(notes):
        drift = (.03 if i % 2 == 0 else -.03) if jitter else 0
        events.extend(((start + (note.start-offset)*60/bpm + drift, note.pitch, True),
                       (start + (note.end-offset)*60/bpm + drift, note.pitch, False)))
    for at, pitch, down in sorted(events):
        send(e, now, at, pitch, down)
        e.state()


def boundary(e, now, end):
    now[0] = e.run_at + (end-e.play_from_beat)*60/e.plan.bpm + .03
    return e.state()


def after_break(e, now):
    now[0] = e.next_at + .01
    state = e.state()
    if state['phase'] == 'loading':
        e.geometry()
        e.control('score_ready', revision=state['revision'])
    return e.state()


def fail_later_chunk(e, now, grid):
    play(e, now, before=grid[2], jitter=True)
    assert boundary(e, now, grid[2])['phase'] == 'playing'
    now[0] = e.run_at + (grid[-1]-.1)*60/e.plan.bpm
    assert e.state()['phase'] == 'playing'  # Never stop before the two-bar ending.
    return boundary(e, now, grid[-1])


@pytest.mark.parametrize('bpm', (30, 40, 80, 120))
@pytest.mark.parametrize('mixed', (False, True))
def test_repeated_failed_chunk_teaches_exact_source_then_returns_to_its_count_in(lesson, bpm, mixed):
    e, now, grid = lesson(bpm, mixed)
    original = e.plan.identity
    first = fail_later_chunk(e, now, grid)
    expected_range = {'first_bar': 3, 'last_bar': 4, 'start_beat': grid[2], 'end_beat': grid[4]}
    assert first['retry_range'] == expected_range
    assert first['bpm'] == round(bpm*.9) and first['target_bpm'] == bpm
    assert 'Retry bars 3-4' in first['next_action']
    assert first['transition_in_seconds'] == pytest.approx(1.5)
    retry = after_break(e, now)
    assert retry['phase'] == 'count_in' and retry['play_from_beat'] == grid[2]
    second = boundary(e, now, grid[-1])
    assert second['phase'] == 'recovering' and second['guided_recovery']
    assert 'Learn bars 3-4' in second['next_action']
    guided = after_break(e, now)
    assert guided['mode'] == 'learn' and guided['phase'] == 'guided_wait'
    assert guided['teaching']['fragment'] == expected_range
    assert guided['first_bar'] == 3 and guided['last_bar'] == 4
    assert guided['required_notes'] == grid[-1]-grid[2]
    assert e.plan.identity == original and e.plan.target_bpm == bpm
    while e.state()['phase'] == 'guided_wait':
        expected = e.state()['teaching']['expected_notes']
        for target in expected:
            send(e, now, now[0]+.05, target['pitch'])
        for target in expected:
            send(e, now, now[0]+.05, target['pitch'], False)
    complete = e.state()
    assert complete['phase'] == 'guided_complete' and complete['mastered'] == 0
    assert complete['streak'] == 0 and 'rhythm' in complete['next_action'].lower()
    slowed = complete['bpm']
    e.control('practice')
    waiting = e.state()
    assert waiting['phase'] == 'loading' and waiting['required_notes'] == grid[-1]
    assert waiting['guided_recovery']
    e.control('score_ready', revision=waiting['revision']-1)
    assert e.state()['phase'] == 'loading'
    e.geometry()
    e.control('score_ready', revision=waiting['revision'])
    returned = e.state()
    assert returned['phase'] == 'count_in' and returned['play_from_beat'] == grid[2]
    assert returned['bpm'] == slowed and returned['target_bpm'] == bpm
    play(e, now, jitter=True)
    now[0] = e.run_at+(grid[-1]-grid[2])*60/slowed+.22
    partial = e.state()
    assert partial['phase'] == 'recovering' and partial['mastered'] == 0 and partial['streak'] == 0
    assert 'whole passage' in partial['next_action'].lower()
    assert after_break(e, now)['play_from_beat'] == 0


def test_feedback_pause_freezes_break_and_does_not_commit_clean_mastery(lesson):
    e, now, grid = lesson()
    for expected_streak in (1, 2):
        play(e, now, jitter=True)
        now[0] = e.run_at + grid[-1]*60/e.plan.bpm + .22
        state = e.state()
        assert f'Clean pass {expected_streak}/3' in state['next_action']
        after_break(e, now)
    play(e, now, jitter=True)
    now[0] = e.run_at + grid[-1]*60/e.plan.bpm + .22
    feedback = e.state()
    assert 'Clean pass 3/3' in feedback['next_action']
    identity = e.plan.identity
    now[0] += .4
    e.control('pause')
    paused = e.state()
    assert paused['phase'] == 'paused' and paused['pause_context'] == 'feedback'
    remaining = paused['transition_in_seconds']
    now[0] += 100
    assert e.state()['transition_in_seconds'] == pytest.approx(remaining)
    assert e.plan.identity == identity and not e.plan.mastered and e.plan.streak == 2
    e.control('resume')
    now[0] += remaining-.01
    assert e.state()['phase'] == 'feedback' and not e.plan.mastered
    now[0] += .02
    assert e.state()['phase'] == 'ready' and identity in e.plan.mastered


@pytest.mark.parametrize('action', ('start', 'restart', 'stop'))
def test_failed_full_take_cannot_preserve_clean_streak_when_feedback_is_abandoned(lesson, action):
    e, now, grid = lesson(120)
    e.fingerprint = 'consecutive-full-takes'
    stage = e.plan.identity
    for _ in range(2):
        finish_take(e, now, 16)
        after_break(e, now)
    assert e.plan.streak == 2

    # One missed final note is below the five-error recovery threshold.
    play(e, now, before=15)
    now[0] = e.run_at + 16 * 60 / 120 + .22
    failed = e.state()
    assert failed['phase'] == 'feedback'
    assert e.pending_result.correct == 15 and len(e.pending_result.notes) == 16
    assert failed['streak'] == 0
    assert e.db.execute('SELECT streak FROM sessions WHERE fingerprint=?',
                        (e.fingerprint,)).fetchone() == (0,)

    e.control(action)
    assert e.pending_result is None and e.plan.streak == 0
    if action == 'stop':
        e.control('start')
    for expected in (1, 2):
        finish_take(e, now, 16)
        after_break(e, now)
        assert e.plan.streak == expected and stage not in e.plan.mastered
    finish_take(e, now, 16)
    after_break(e, now)
    assert e.plan.mastered[stage] == 120


def test_failed_full_imported_practice_repeats_after_its_feedback_interval(lesson):
    e, now, _ = lesson(120)
    stage, transport = e.plan.identity, e.transport_id
    play(e, now, before=15)
    now[0] = e.run_at + 16 * 60 / 120 + .22
    failed = e.state()
    assert failed['phase'] == 'feedback' and e.pending_result.correct == 15
    assert e.next_at > now[0]
    now[0] = e.next_at - .01
    assert e.state()['phase'] == 'feedback' and e.transport_id == transport
    repeated = after_break(e, now)
    assert repeated['phase'] == 'count_in' and e.transport_id == transport + 1
    assert e.plan.identity == stage and repeated['play_from_beat'] == 0
    assert repeated['streak'] == 0 and not e.plan.mastered


@pytest.mark.parametrize('guided', (False, True))
def test_loading_pause_defers_current_score_ack_and_rejects_stale_ack(lesson, guided):
    e, now, _ = lesson()
    e.control('learn' if guided else 'practice')
    revision = e.state()['revision']
    e.control('pause')
    assert e.state()['phase'] == 'paused' and e.state()['pause_context'] == 'loading'
    e.control('score_ready', revision=revision-1)
    e.control('score_ready', revision=revision)
    now[0] += 100
    assert e.state()['phase'] == 'paused' and not e.state()['running']
    old_id = e.transport_id
    e.control('resume')
    result = e.state()
    assert result['phase'] == ('guided_wait' if guided else 'count_in')
    assert e.transport_id == (old_id if guided else old_id+1)
    assert result['clock_beat'] <= 0


def test_recovery_pause_freezes_retry_then_stop_cancels_it(lesson):
    e, now, grid = lesson()
    fail_later_chunk(e, now, grid)
    now[0] += .5
    e.control('pause')
    state = e.state()
    assert state['phase'] == 'paused' and state['pause_context'] == 'recovering'
    remaining = state['transition_in_seconds']
    now[0] += 200
    assert e.state()['transition_in_seconds'] == pytest.approx(remaining)
    assert e.state()['bpm'] == 72
    e.control('resume')
    now[0] += remaining-.01
    assert e.state()['phase'] == 'recovering'
    now[0] += .02
    waiting = e.state()
    assert waiting['phase'] == 'loading'
    e.control('pause')
    e.control('score_ready', revision=waiting['revision'])
    e.control('stop')
    now[0] += 500
    assert e.state()['phase'] == 'ready' and not e.state()['running']
    assert not e.plan.mastered


def test_no_device_preview_never_enters_retry_or_guided_recovery(lesson):
    e, now, grid = lesson(30, True, connected=False)
    now[0] = e.run_at + grid[-1]*60/e.plan.bpm + .22
    state = e.state()
    assert state['phase'] == 'preview_gap' and not state['guided_recovery']
    assert state['preview_only'] and not state['running']
    assert state['retry_range'] is None and state['mastered'] == 0
    assert state['take_result'] is None
    assert 'piano' in state['next_action'].lower()
    revision = e.score_revision
    now[0] = e.next_at + .01
    repeated = e.state()
    assert repeated['phase'] == 'playing' and repeated['preview_only']
    assert repeated['retry_range'] is None and not repeated['guided_recovery']
    assert repeated['mastered'] == 0 and repeated['revision'] == revision


def finish_take(e, now, end, *, jitter=True):
    play(e, now, jitter=jitter)
    now[0] = e.run_at+(end-e.play_from_beat)*60/e.plan.bpm+.22
    return e.state()


def complete_guidance(e, now):
    while e.state()['phase'] == 'guided_wait':
        targets = e.state()['teaching']['expected_notes']
        for target in targets:
            send(e, now, now[0]+.04, target['pitch'])
        for target in targets:
            send(e, now, now[0]+.04, target['pitch'], False)
    assert e.state()['phase'] == 'guided_complete'
    e.control('practice')
    waiting = e.state()
    e.geometry()
    e.control('score_ready', revision=waiting['revision'])


def test_entire_recovery_restores_chosen_tempo_then_three_full_takes_reveal_chord_notes(lesson):
    e, now, grid = lesson(80, chords=True)
    assert e.state()['lesson_level'] == 'skeleton'
    stage = e.plan.identity
    fail_later_chunk(e, now, grid)
    after_break(e, now)
    boundary(e, now, grid[-1])
    after_break(e, now)
    complete_guidance(e, now)
    assert e.play_from_beat == 8 and e.plan.bpm == 65 and e.plan.target_bpm == 80
    assert finish_take(e, now, 16)['phase'] == 'recovering'
    assert not e.plan.mastered and e.plan.streak == 0
    after_break(e, now)
    while e.plan.bpm < e.plan.target_bpm:
        before = e.plan.bpm
        after = e.plan._next_automatic_bpm()
        assert after > before
        feedback = finish_take(e, now, 16)
        assert 'restore tempo' in feedback['next_action'] and f'{after} BPM' in feedback['next_action']
        assert feedback['streak'] == 0 and not e.plan.mastered
        after_break(e, now)
        assert e.plan.bpm == after and e.plan.target_bpm == 80
    for streak in (1, 2, 3):
        feedback = finish_take(e, now, 16)
        assert f'Clean pass {streak}/3' in feedback['next_action']
        assert 'course:' not in feedback['next_action']
        assert stage not in e.plan.mastered
        if streak == 3:
            assert 'restore missing chord notes' in feedback['next_action']
            now[0] = e.next_at+.01
            loading = e.state()
            assert loading['phase'] == 'loading' and loading['lesson_level'] == 'outline'
            assert loading['next_action'] == feedback['next_action']
            assert e.plan.mastered[stage] == 80 and e.plan.target_bpm == 80
        else:
            after_break(e, now)
    # The mastered source stage gains pitches; it never substitutes a new song.
    assert len(e.plan.active_phrase.notes) == 32
    assert e.plan.index == 0 and e.plan.hand == 'right'


def test_clean_full_take_resets_repeated_trouble_before_a_later_failure(lesson):
    e, now, grid = lesson()
    fail_later_chunk(e, now, grid)
    after_break(e, now)
    finish_take(e, now, 16)
    after_break(e, now)  # Whole-passage check after the clean partial.
    assert finish_take(e, now, 16)['phase'] == 'feedback'
    after_break(e, now)
    state = fail_later_chunk(e, now, grid)
    assert not state['guided_recovery'] and 'Retry bars 3-4' in state['next_action']


def test_manual_stage_selection_resets_trouble_and_invalidates_old_recovery(lesson):
    e, now, grid = lesson(chords=True)
    fail_later_chunk(e, now, grid)
    revision = e.state()['revision']
    e.control('hand', hand='right')
    e.control('score_ready', revision=revision)
    assert e.state()['phase'] == 'ready' and e.state()['retry_range'] is None
    e.start()
    state = fail_later_chunk(e, now, grid)
    assert not state['guided_recovery']


@pytest.mark.parametrize('bpm', (30, 40, 80, 120))
def test_only_five_distinct_wrong_or_missed_notes_trigger_after_boundary(lesson, bpm):
    e, now, grid = lesson(bpm)
    play(e, now, before=8, jitter=True)
    boundary(e, now, 8)
    # Three correct notes, two wrong pitches, three silence misses: exactly five.
    for beat in (8, 9, 10, 11, 12):
        pitch = (60, 62, 64, 65)[beat % 4] if beat < 11 else 90
        at = e.run_at+beat*60/bpm+.03
        send(e, now, at, pitch)
        send(e, now, at+.5*60/bpm, pitch, False)
    now[0] = e.run_at + 15.99*60/bpm
    assert e.state()['phase'] == 'playing'
    state = boundary(e, now, 16)
    assert state['phase'] == 'recovering'
    assert state['feedback'].startswith('5 wrong or missed notes')
    assert state['retry_range']['first_bar'] == 3


@pytest.mark.parametrize('mixed,misses', ((False, (4, 5, 6, 8, 9)),
                                        (True, (3, 4, 5, 6, 7))))
def test_rolling_errors_cross_chunk_boundary_but_retry_current_canonical_idea(lesson, mixed, misses):
    e, now, grid = lesson(120, mixed=mixed)
    e.fingerprint = 'rolling-source-errors'
    play(e, now, omit=misses)
    now[0] = e.run_at + (grid[-1]-.01)*.5
    assert e.state()['phase'] == 'playing'  # Threshold never stops mid-chunk.
    state = boundary(e, now, grid[-1])
    assert state['phase'] == 'recovering' and state['bpm'] == 108
    assert state['recovery_notice']['errors'] == 5
    assert state['retry_range'] == {'first_bar': 3, 'last_bar': 4,
                                   'start_beat': grid[2], 'end_beat': grid[4]}
    trouble = e.lesson_overview()['trouble_spots']
    assert len(trouble) == 1
    assert trouble[0]['first_bar'] == 3 and trouble[0]['errors'] == 2
    assert after_break(e, now)['play_from_beat'] == grid[2]

    # A subsequent failure of this canonical idea still opens exact Learn help.
    second = boundary(e, now, grid[-1])
    assert second['guided_recovery'] and second['phase'] == 'recovering'
    guided = after_break(e, now)
    assert guided['mode'] == 'learn' and guided['phase'] == 'guided_wait'
    assert (guided['first_bar'], guided['last_bar']) == (3, 4)
    assert not e.plan.mastered and e.plan.streak == 0


@pytest.mark.parametrize('mixed,misses', ((False, (4, 5, 8, 9)),
                                        (True, (3, 4, 6, 7))))
def test_four_rolling_misses_keep_playing_without_slowdown(lesson, mixed, misses):
    e, now, grid = lesson(120, mixed=mixed)
    play(e, now, omit=misses)
    state = boundary(e, now, grid[-1])
    assert state['phase'] == 'playing' and state['bpm'] == 120
    assert state['retry_range'] is None and not e.plan.mastered


def test_live_miss_appears_after_release_grace_and_score_keeps_moving_through_rest(lesson):
    e, now, _ = lesson(80)
    now[0] = e.run_at + .5*60/80+.10
    before = e.state()
    assert not [m for m in before['feedback_marks'] if m['beat'] == 0]
    now[0] += .03
    settled = e.state()
    assert any(m['beat'] == 0 and m['status'] == 'missed' for m in settled['feedback_marks'])
    beat = settled['clock_beat']
    now[0] += .05
    moving = e.state()
    assert moving['phase'] == 'playing' and moving['clock_beat'] > beat


def test_only_stale_ack_during_paused_loading_leaves_score_waiting_on_resume(lesson):
    e, now, _ = lesson()
    e.control('practice')
    revision = e.state()['revision']
    e.control('pause')
    e.control('score_ready', revision=revision-1)
    now[0] += 10
    e.control('resume')
    assert e.state()['phase'] == 'loading' and not e.state()['running']
    e.control('score_ready', revision=revision)
    assert e.state()['phase'] == 'count_in'


def test_disconnected_piano_replaces_old_play_instruction(lesson):
    e, _, _ = lesson()
    class ClosedPiano:
        closed = True
    e.midi_port = ClosedPiano()
    state = e.state()
    assert state['phase'] == 'ready'
    assert 'piano' in state['next_action'].lower() and 'connect' in state['next_action'].lower()


def test_loading_piece_starts_new_trouble_history_and_fresh_instruction(lesson, tmp_path, monkeypatch):
    e, now, grid = lesson()
    fail_later_chunk(e, now, grid)
    piece = e.plan.piece
    path = tmp_path / 'reimport.mid'
    path.write_bytes(b'controlled import fixture')
    monkeypatch.setattr(server, 'import_piece', lambda _: (piece, object()))
    e.load(str(path))
    # Reimport is tested using the original four-bar error window.
    e.plan = LearningPlan(e.plan.piece, consolidate=True)
    ready = e.state()
    assert 'Start' in ready['next_action']
    assert ready['retry_range'] is None
    e.plan.set_bpm(80)
    e.geometry()
    e.start()
    state = fail_later_chunk(e, now, grid)
    assert not state['guided_recovery']


@pytest.mark.parametrize('context', ('feedback', 'recovering', 'loading'))
def test_resume_preserves_instructional_feedback_during_automatic_transition(lesson, context):
    e, now, grid = lesson()
    if context == 'feedback':
        before = finish_take(e, now, grid[-1])
    elif context == 'recovering':
        before = fail_later_chunk(e, now, grid)
    else:
        e.control('practice')
        before = e.state()
    assert before['phase'] == context
    e.control('pause')
    assert e.state()['phase'] == 'paused'
    now[0] += 10
    e.control('resume')
    resumed = e.state()
    assert resumed['phase'] == context
    assert resumed['feedback'] == before['feedback']
    assert resumed['next_action'] == before['next_action']


def test_five_error_recovery_animates_backward_on_same_score(lesson):
    # Actual timestamped note_on/off callbacks, not an injected decision.
    e, now, grid = lesson()
    revision = e.score_revision
    first = fail_later_chunk(e, now, grid)
    assert first["phase"] == "recovering"
    assert first["visual_scroll_speed"] < 0
    assert first["visual_target_beat"] == pytest.approx(grid[2])
    assert first["visual_scroll_beat"] > first["visual_target_beat"]
    assert first["revision"] == revision
    now[0] = e.next_at - .05
    nearly = e.state()
    assert nearly["visual_scroll_beat"] >= grid[2]
    assert nearly["visual_scroll_beat"] < first["visual_scroll_beat"]
    now[0] = e.next_at + .01
    repeated = e.state()
    assert repeated["phase"] == "playing"
    assert repeated["play_from_beat"] == pytest.approx(grid[2])
    assert repeated["visual_scroll_beat"] == pytest.approx(grid[2], abs=.1)
    assert repeated["revision"] == revision
    assert repeated["count_in_beats"] == 0
