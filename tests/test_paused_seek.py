"""Seeking while paused starts a fresh source-measure attempt."""
import pytest
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from test_instructional_recovery import lesson, send, play, finish_take, after_break
from test_listen_perform import acknowledge


@pytest.mark.parametrize('mode', ('practice', 'perform'))
@pytest.mark.parametrize('mixed', (False, True))
def test_paused_seek_reloads_practice_at_source_bar_with_fresh_count_in(lesson, mode, mixed):
    e, now, grid = lesson(80, mixed)
    if mode == 'perform':
        e.control('perform')
        acknowledge(e)
    now[0] = e.run_at+.2
    send(e, now, now[0], 90)
    e.control('pause')
    before = e.state()
    assert before['seek_available']
    assert before['seek_range'] == {'first_bar': 1, 'last_bar': 4}
    e.control('seek', bar=3)
    waiting = e.state()
    assert waiting['mode'] == 'practice' and waiting['phase'] == 'loading'
    assert waiting['revision'] > before['revision']
    assert waiting['bpm'] == waiting['target_bpm'] == 80
    assert waiting['recovery_beat'] == grid[2]
    e.control('score_ready', revision=before['revision'])
    assert e.state()['phase'] == 'loading'
    started = acknowledge(e)
    assert started['phase'] == 'count_in' and started['play_from_beat'] == grid[2]
    assert started['midi_notes'] == 0 and started['clock_beat'] < 0
    partial = finish_take(e, now, grid[-1])
    assert partial['phase'] == 'recovering' and partial['streak'] == 0
    assert not e.plan.mastered
    assert after_break(e, now)['play_from_beat'] == 0


def test_guided_seek_uses_active_passage_bounds_and_preserves_held_key_blocking(lesson):
    e, now, _ = lesson()
    e.control('learn')
    acknowledge(e)
    send(e, now, now[0]+.1, 60)
    e.control('pause')
    before = e.state()
    assert before['last_bar'] == 2 and before['seek_range']['last_bar'] == 4
    e.control('seek', bar=3)
    waiting = e.state()
    assert waiting['mode'] == 'learn' and waiting['phase'] == 'loading'
    assert waiting['first_bar'] == 3 and waiting['last_bar'] == 4
    assert waiting['teaching']['fragment']['start_beat'] == 8
    e.control('score_ready', revision=before['revision'])
    send(e, now, now[0]+.1, 60)
    assert e.state()['phase'] == 'loading'
    acknowledge(e)
    send(e, now, now[0]+.1, 60)
    assert e.state()['teaching']['target_index'] == 0
    send(e, now, now[0]+.1, 60, False)
    send(e, now, now[0]+.1, 60)
    assert e.state()['teaching']['target_index'] == 1
    assert not e.plan.mastered and e.plan.streak == 0


@pytest.mark.parametrize('bar', (0, 5, -1, 1.5, True, '3', None))
def test_invalid_seek_leaves_paused_attempt_and_revision_intact(lesson, bar):
    e, now, _ = lesson()
    e.control('pause')
    before = e.state()
    with pytest.raises(ValueError):
        e.control('seek', bar=bar)
    now[0] += 10
    after = e.state()
    assert after['phase'] == 'paused'
    assert after['revision'] == before['revision'] and after['transport_id'] == before['transport_id']
    assert after['clock_beat'] == before['clock_beat']
    assert after['bpm'] == before['bpm']


def test_seek_rejects_unpaused_and_listen_without_abandoning_transport(lesson):
    e, _, _ = lesson()
    before = e.state()
    with pytest.raises(ValueError):
        e.control('seek', bar=3)
    assert e.state()['phase'] == before['phase'] and e.state()['running']
    e.control('listen')
    acknowledge(e)
    e.control('pause')
    before = e.state()
    assert not before['seek_available']
    with pytest.raises(ValueError):
        e.control('seek', bar=3)
    after = e.state()
    assert after['mode'] == 'listen' and after['phase'] == 'paused'
    assert after['demo']['token'] == before['demo']['token']


def test_seek_bar_number_is_absolute_within_source_and_start_bar_remains_full_attempt(lesson):
    e, now, _ = lesson()
    notes = tuple(Note(float(i), i+.5, (60, 62, 64, 65)[i % 4], 0, 0, 'right')
                  for i in range(8, 24))
    e.plan = LearningPlan(Piece('Later source passage', 80, notes,
        (Phrase(1, 3, 6, 8, 24, notes),), bar_boundaries=(0, 4, 8, 12, 16, 20, 24),
        time_signatures=((0, 4, 4),)))
    e.plan.set_bpm(80)
    e.start()
    e.control('pause')
    assert e.state()['seek_range'] == {'first_bar': 3, 'last_bar': 6}
    e.control('seek', bar=4)
    started = acknowledge(e)
    assert started['play_from_beat'] == 4
    e.control('pause')
    e.control('seek', bar=3)
    assert acknowledge(e)['play_from_beat'] == 0


def test_seek_unavailable_without_authoritative_source_measure_grid(lesson):
    e, _, _ = lesson()
    phrase = e.plan.active_phrase
    e.plan = LearningPlan(Piece('Legacy synthetic grid', 80, phrase.notes, (phrase,)))
    e.start()
    e.control('pause')
    assert not e.state()['seek_available']
    with pytest.raises(ValueError):
        e.control('seek', bar=3)
    assert e.state()['phase'] == 'paused'


def test_seek_abandons_paused_feedback_without_committing_its_clean_result(lesson):
    e, now, _ = lesson()
    for _ in range(2):
        finish_take(e, now, 16)
        after_break(e, now)
    feedback = finish_take(e, now, 16)
    assert feedback['phase'] == 'feedback' and e.plan.streak == 2
    e.control('pause')
    e.control('seek', bar=3)
    assert e.pending_result is None and not e.plan.mastered
    acknowledge(e)
    assert e.play_from_beat == 8
    partial = finish_take(e, now, 16)
    assert partial['phase'] == 'recovering' and not e.plan.mastered
