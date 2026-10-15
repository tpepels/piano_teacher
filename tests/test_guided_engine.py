"""Learner MIDI reaches guided teaching through the real backend callback."""
import mido
import pytest

from piano_teacher import server
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.server import PracticeEngine


@pytest.fixture
def learner(tmp_path, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(server.time, 'monotonic', lambda: now[0])
    notes = (Note(0, 2, 60, 0, 0), Note(2, 3, 60, 0, 0),
             Note(4, 5, 64, 0, 0), Note(4, 5, 67, 0, 0),
             Note(8, 9, 65, 0, 0), Note(12, 13, 69, 0, 0))
    phrases = (Phrase(1, 1, 2, 0, 8, notes[:4]),
               Phrase(2, 3, 4, 8, 16, notes[4:]))
    e = PracticeEngine(tmp_path, enable_midi=False)
    e.plan = LearningPlan(Piece('Imported idea', 120, notes, phrases,
                               bar_boundaries=(0, 4, 8, 12, 16),
                               time_signatures=((0, 4, 4),)))
    e.plan.variant_index = len(e.plan.variants) - 1
    e.plan.set_bpm(120)
    e.midi_port = object()
    e.midi_device = 'Test piano'
    try:
        yield e, now
    finally:
        e.db.close()


def send(e, pitch, down=True):
    e._receive(mido.Message('note_on' if down else 'note_off', note=pitch,
                           velocity=80 if down else 0))


def begin(e):
    e.control('learn')
    waiting = e.state()
    e.geometry()  # Real fragment engraving, using the active generated notes.
    e.control('score_ready', revision=waiting['revision'])
    return e.state()


def test_guided_waits_for_correct_fresh_attacks_at_any_speed_and_never_masters(learner):
    e, now = learner
    e.plan.streak = 2
    state = begin(e)
    assert state['mode'] == 'learn' and state['phase'] == 'guided_wait'
    assert not state['running'] and state['clock_beat'] == 0
    assert state['first_bar'] == 1 and state['last_bar'] == 2
    assert state['required_notes'] == 4
    assert [n['pitch'] for n in state['teaching']['expected_notes']] == [60]
    send(e, 61)
    wrong = e.state()
    assert wrong['teaching']['target_index'] == 0
    assert wrong['teaching']['hint_visible']
    assert any(mark['status'] == 'wrong' for mark in wrong['feedback_marks'])
    send(e, 61, False)
    now[0] += 30  # Learn has no timed miss or automatic cursor movement.
    send(e, 60)
    assert e.state()['teaching']['target_index'] == 1
    send(e, 60)  # Holding/repeated note-on cannot satisfy the repeated pitch.
    assert e.state()['teaching']['target_index'] == 1
    send(e, 60, False)
    now[0] += 12
    send(e, 60)
    send(e, 60, False)
    send(e, 64)
    now[0] += .1
    send(e, 67)
    done = e.state()
    assert done['phase'] == 'guided_complete'
    assert done['teaching']['completed']
    assert done['teaching']['assisted_count'] >= 1
    assert not done['teaching']['mastery_eligible']
    assert e.plan.streak == 2 and e.plan.mastered == {}
    assert e.pending_result is None and e.recorder is None and not e.auto
    assert e.plan.bpm == 120


def test_guided_score_ack_is_revision_bound_and_practice_restores_full_active_variant(learner):
    e, _ = learner
    e.control('learn')
    revision = e.state()['revision']
    e.control('score_ready', revision=revision - 1)
    send(e, 60)
    assert e.state()['teaching']['target_index'] == 0
    assert e.state()['phase'] == 'loading'
    e.control('score_ready', revision=revision)
    send(e, 60, False)
    send(e, 60)
    assert e.state()['teaching']['target_index'] == 1
    e.control('practice')
    waiting = e.state()
    assert waiting['mode'] == 'practice' and waiting['phase'] == 'loading'
    assert waiting['required_notes'] == 6 and waiting['last_bar'] == 4
    e.control('score_ready', revision=revision)
    assert e.state()['phase'] == 'loading'
    e.geometry()
    e.control('score_ready', revision=waiting['revision'])
    playing = e.state()
    assert playing['phase'] == 'count_in' and playing['running']
    assert playing['target_bpm'] == 120 and playing['streak'] == 0
    assert playing['teaching'] is None


def test_guided_pause_stop_retry_and_stage_change_clear_old_keys(learner):
    e, now = learner
    begin(e)
    send(e, 60)
    e.control('pause')
    now[0] += 100
    send(e, 60, False)
    send(e, 60)
    assert e.state()['phase'] == 'paused'
    assert e.state()['teaching']['target_index'] == 1
    e.control('resume')
    send(e, 60)
    assert e.state()['teaching']['target_index'] == 1
    send(e, 60, False)
    send(e, 60)
    assert e.state()['teaching']['target_index'] == 2
    e.control('learn_retry')
    fresh = e.state()
    e.control('score_ready', revision=fresh['revision'])
    assert e.state()['teaching']['target_index'] == 0
    send(e, 60)
    assert e.state()['teaching']['target_index'] == 0
    send(e, 60, False)
    send(e, 60)
    assert e.state()['teaching']['target_index'] == 1
    old = e.state()['revision']
    e.control('next')
    assert e.state()['revision'] > old
    assert e.state()['mode'] == 'learn'
    assert e.state()['teaching']['target_index'] == 0
    e.control('score_ready', revision=old)
    send(e, 60)
    assert e.state()['phase'] == 'loading'
    e.control('stop')
    send(e, 60)
    assert e.state()['phase'] == 'ready' and not e.state()['running']
    assert e.plan.streak == 0 and not e.plan.mastered


def test_no_device_cannot_progress_guided_but_timed_preview_is_available(learner):
    e, _ = learner
    e.midi_port = None
    e.midi_device = ''
    state = begin(e)
    assert state['phase'] == 'disconnected'
    send(e, 60)  # Even stale callbacks after device loss cannot teach a note.
    assert e.state()['teaching']['target_index'] == 0
    assert 'piano' in e.state()['feedback'].lower()
    e.control('practice')
    e.control('score_ready', revision=e.state()['revision'])
    assert e.state()['phase'] == 'count_in' and e.state()['preview_only']
    assert not e.plan.mastered


def test_guided_marks_and_expected_ids_use_the_displayed_generated_fragment(learner):
    e, _ = learner
    state = begin(e)
    layout = e.geometry()
    expected = state['teaching']['expected_notes'][0]
    assert expected['id'].startswith(e.plan.identity + ':')
    assert expected['label'] == 'C4'
    assert any(n['pitch'] == expected['pitch'] and n['beat'] == expected['beat']
               for n in layout['notes'])
    assert any(mark['status'] == 'expected' for mark in state['feedback_marks'])
    e.control('hints', enabled=True)
    assert e.state()['teaching']['hint_visible']
    send(e, 60)
    assert any(mark['status'] == 'assisted' for mark in e.state()['feedback_marks'])
    assert e.state()['streak'] == 0


def test_direct_timed_start_after_learn_waits_for_full_variant_geometry(learner):
    e, _ = learner
    begin(e)
    old = e.state()['revision']
    e.start()
    state = e.state()
    assert state['mode'] == 'practice'
    assert state['phase'] == 'loading'
    assert state['revision'] > old
    assert state['required_notes'] == 6


def test_closed_input_port_blocks_stale_callbacks_before_next_discovery_poll(learner):
    e, _ = learner
    begin(e)
    class ClosedPort:
        closed = True
    e.midi_port = ClosedPort()
    send(e, 60)
    state = e.state()
    assert state['phase'] == 'disconnected'
    assert state['teaching']['target_index'] == 0
    assert not e.plan.mastered and e.recorder is None


def test_release_during_guided_render_unlocks_the_next_fresh_attack(learner):
    e, _ = learner
    begin(e)
    send(e, 60)
    e.control('learn_retry')
    send(e, 60, False) # Physical releases still matter while geometry loads.
    e.control('score_ready', revision=e.state()['revision'])
    send(e, 60)
    assert e.state()['teaching']['target_index'] == 1


def test_key_pressed_while_loading_cannot_be_reused_as_a_fresh_answer(learner):
    e, _ = learner
    e.control('learn')
    send(e, 60)
    e.control('score_ready', revision=e.state()['revision'])
    send(e, 60)
    assert e.state()['teaching']['target_index'] == 0
    send(e, 60, False)
    send(e, 60)
    assert e.state()['teaching']['target_index'] == 1
