"""Guided preparation and trouble history persist without inventing mastery."""
import math
import sqlite3

import pytest

from piano_teacher import learner_state
from piano_teacher.exercise_generator import ExerciseVariant
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece


def imported_variant():
    # A source excerpt beginning at bar3 crosses from3/4 to4/4, then has
    # an entirely silent final2-bar idea which belongs in timed Practice.
    notes = (Note(6, 7, 60, 0, 0), Note(11, 12, 64, 0, 0),
             Note(12, 13, 67, 0, 0), Note(19, 21, 69, 0, 0))
    phrase = Phrase(2, 3, 8, 6, 28, notes)
    return ExerciseVariant('outline', phrase, (5, 8, 12, 16)), (0, 3, 6, 9, 12, 16, 20, 24, 28)


def test_guided_units_follow_source_meter_and_exact_active_variant_ids():
    variant, boundaries = imported_variant()
    units = learner_state.guided_units(variant, boundaries)
    assert units == (
        {'first_bar': 3, 'last_bar': 4, 'start_beat': 0., 'end_beat': 6.,
         'source_indices': [5, 8], 'required_notes': 2},
        {'first_bar': 5, 'last_bar': 6, 'start_beat': 6., 'end_beat': 14.,
         'source_indices': [12, 16], 'required_notes': 2},
    )
    assert variant.phrase.end == 28  # No guided unit may remove timed rests.


def test_no_input_creates_no_progress_and_next_idea_is_first_source_unit(tmp_path):
    db = sqlite3.connect(tmp_path/'learner.db')
    store = learner_state.LearnerStateStore(db)
    variant, boundaries = imported_variant()
    state = store.read('piece', 'stage')
    assert state == {'resume_unit': None, 'completed_units': [], 'trouble_units': [],
                     'skip_status': 'active', 'skip_reason': ''}
    assert learner_state.next_guided_unit(variant, boundaries, state)['source_indices'] == [5, 8]
    assert not store.trouble_for_piece('piece')
    assert db.execute('SELECT count(*) FROM learner_stages').fetchone()[0] == 0
    db.close()


def test_resume_and_assisted_unit_completion_survive_reopen_without_touching_saved_mastery(tmp_path):
    path = tmp_path/'learner.db'
    db = sqlite3.connect(path)
    db.execute('CREATE TABLE mastery (fingerprint TEXT, exercise TEXT, bpm INTEGER)')
    db.execute('CREATE TABLE sessions (fingerprint TEXT, streak INTEGER, target_bpm INTEGER)')
    db.execute('INSERT INTO sessions VALUES (?, ?, ?)', ('piece', 2, 75))
    db.commit()
    store = learner_state.LearnerStateStore(db)
    variant, boundaries = imported_variant()
    first, second = learner_state.guided_units(variant, boundaries)
    store.save_resume('piece', 'stage', second)
    db.close()
    db = sqlite3.connect(path)
    store = learner_state.LearnerStateStore(db)
    resumed = store.read('piece', 'stage')
    assert resumed['resume_unit'] == second
    assert learner_state.next_guided_unit(variant, boundaries, resumed) == second
    store.complete_unit('piece', 'stage', second, assisted=True)
    after = store.read('piece', 'stage')
    assert after['resume_unit'] is None and after['completed_units'] == [second]
    assert learner_state.next_guided_unit(variant, boundaries, after) == first
    assert db.execute('SELECT * FROM mastery').fetchall() == []
    assert db.execute('SELECT * FROM sessions').fetchall() == [('piece', 2, 75)]
    db.close()


def test_saved_unit_never_leaks_between_pieces_hands_or_source_revisions(tmp_path):
    with sqlite3.connect(tmp_path/'learner.db') as db:
        store = learner_state.LearnerStateStore(db)
        variant, boundaries = imported_variant()
        first, second = learner_state.guided_units(variant, boundaries)
        store.save_resume('piece', 'right:outline:source-a', second)
        store.complete_unit('piece', 'right:outline:source-a', first)
        for fingerprint, stage in [('other', 'right:outline:source-a'),
                                   ('piece', 'left:outline:source-a'),
                                   ('piece', 'right:outline:source-b')]:
            state = store.read(fingerprint, stage)
            assert not state['completed_units'] and state['resume_unit'] is None


def test_stale_unit_source_ids_cannot_skip_changed_notes():
    variant, boundaries = imported_variant()
    units = learner_state.guided_units(variant, boundaries)
    stale = dict(units[0], source_indices=[999, 1000])
    state = {'resume_unit': stale, 'completed_units': [stale, units[1]]}
    assert learner_state.next_guided_unit(variant, boundaries, state) == units[0]


def test_rebound_unit_ids_do_not_inherit_old_preparation_or_trouble(tmp_path):
    with sqlite3.connect(tmp_path/'learner.db') as db:
        store = learner_state.LearnerStateStore(db)
        variant, boundaries = imported_variant()
        first = learner_state.guided_units(variant, boundaries)[0]
        store.complete_unit('piece', 'stage', first)
        store.record_trouble('piece', 'stage', first, errors=5, pitches=[60])
        rebound = dict(first, source_indices=[101, 102])
        store.record_trouble('piece', 'stage', rebound, errors=6, pitches=[72])
        current = store.read('piece', 'stage')
        assert current['completed_units'] == []
        assert current['trouble_units'][0]['source_indices'] == [101, 102]
        assert current['trouble_units'][0]['pitches'] == [72]
        assert current['trouble_units'][0]['failures'] == 1


def test_every_two_bar_idea_of_a_sixteen_bar_import_prepares_then_full_rhythm_is_next(tmp_path):
    notes = tuple(Note(i*4, i*4+1, 60+i%4, 0, 0) for i in range(16))
    phrase = Phrase(1, 1, 16, 0, 64, notes)
    variant = ExerciseVariant('original', phrase, tuple(range(16)))
    boundaries = tuple(range(0, 65, 4))
    with sqlite3.connect(tmp_path/'learner.db') as db:
        store = learner_state.LearnerStateStore(db)
        visited = []
        while (unit := learner_state.next_guided_unit(variant, boundaries, store.read('piece', 'stage'))) is not None:
            visited.append((unit['first_bar'], unit['last_bar']))
            store.save_resume('piece', 'stage', unit)
            store.complete_unit('piece', 'stage', unit, assisted=True)
        assert visited == [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10), (11, 12), (13, 14), (15, 16)]
        assert len(store.read('piece', 'stage')['completed_units']) == 8
        assert variant.phrase.notes == notes and variant.phrase.end == 64


def test_trouble_is_saved_across_stages_and_resolution_is_explicit(tmp_path):
    with sqlite3.connect(tmp_path/'learner.db') as db:
        store = learner_state.LearnerStateStore(db)
        variant, boundaries = imported_variant()
        first, second = learner_state.guided_units(variant, boundaries)
        store.record_trouble('piece', 'right', first, errors=5, pitches=[60, 64, 60])
        store.record_trouble('piece', 'right', first, errors=6, pitches=[65])
        store.record_trouble('piece', 'left', second, errors=7, pitches=[48])
        store.record_trouble('other-piece', 'right', first, errors=8, pitches=[72])
        store.complete_unit('piece', 'right', first)
        trouble = store.read('piece', 'right')['trouble_units'][0]
        assert trouble['failures'] == 2 and trouble['errors'] == 6
        assert trouble['pitches'] == [60, 64, 65]
        assert len(store.trouble_for_piece('piece')) == 2
        assert {spot['stage_key'] for spot in store.trouble_for_piece('piece')} == {'right', 'left'}
        store.resolve_trouble('piece', 'right')
        assert not store.read('piece', 'right')['trouble_units']
        assert [spot['stage_key'] for spot in store.trouble_for_piece('piece')] == ['left']
        assert len(store.trouble_for_piece('piece', include_resolved=True)) == 2
        store.record_trouble('piece', 'right', first, errors=5, pitches=[60])
        assert store.read('piece', 'right')['trouble_units'][0]['failures'] == 1


@pytest.mark.parametrize('status', ['skipped', 'placed'])
def test_skip_and_placement_are_explicit_unmastered_decisions(tmp_path, status):
    with sqlite3.connect(tmp_path/'learner.db') as db:
        db.execute('CREATE TABLE mastery (fingerprint TEXT, exercise TEXT, bpm INTEGER)')
        store = learner_state.LearnerStateStore(db)
        store.mark_skipped('piece', 'stage', reason='Student chose the full original notes', status=status)
        state = store.read('piece', 'stage')
        assert state['skip_status'] == status
        assert state['skip_reason'] == 'Student chose the full original notes'
        assert state['completed_units'] == [] and db.execute('SELECT * FROM mastery').fetchall() == []
        store.reactivate('piece', 'stage')
        assert store.read('piece', 'stage')['skip_status'] == 'active'


def test_optional_placement_only_suggests_current_hand_original_without_changing_plan():
    notes = tuple(Note(i, i+.8, pitch, 0, 0) for i in range(8) for pitch in (60, 64, 67))
    phrase = Phrase(1, 1, 2, 0, 8, notes)
    plan = LearningPlan(Piece('Imported chords', 80, notes, (phrase,)))
    before = (plan.identity, plan.streak, dict(plan.mastered), plan.bpm)
    candidate = learner_state.placement_candidate(plan)
    assert candidate.exercise_index == 0 and candidate.hand == 'right' and candidate.level == 'original'
    assert candidate.required_notes == 24
    assert (plan.identity, plan.streak, plan.mastered, plan.bpm) == before
    plan.variant_index = len(plan.variants)-1
    assert learner_state.placement_candidate(plan) is None


@pytest.mark.parametrize('operation', [
    lambda store, unit: store.save_resume('', 'stage', unit),
    lambda store, unit: store.save_resume('piece', '', unit),
    lambda store, unit: store.save_resume('piece', 'stage', dict(unit, start_beat=-1)),
    lambda store, unit: store.save_resume('piece', 'stage', dict(unit, end_beat=math.inf)),
    lambda store, unit: store.save_resume('piece', 'stage', dict(unit, end_beat=0)),
    lambda store, unit: store.save_resume('piece', 'stage', dict(unit, source_indices=[1, 1])),
    lambda store, unit: store.record_trouble('piece', 'stage', unit, errors=0),
    lambda store, unit: store.record_trouble('piece', 'stage', unit, errors=5, pitches=[128]),
    lambda store, unit: store.mark_skipped('piece', 'stage', reason='', status='skipped'),
    lambda store, unit: store.mark_skipped('piece', 'stage', reason='Requested', status='mastered'),
])
def test_invalid_state_cannot_create_false_progress(tmp_path, operation):
    with sqlite3.connect(tmp_path/'learner.db') as db:
        store = learner_state.LearnerStateStore(db)
        variant, boundaries = imported_variant()
        unit = learner_state.guided_units(variant, boundaries)[0]
        with pytest.raises(ValueError):
            operation(store, unit)
        assert store.read('piece', 'stage')['completed_units'] == []
        assert store.read('piece', 'stage')['resume_unit'] is None
