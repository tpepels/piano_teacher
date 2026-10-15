"""Imported-source learner progression stays separate from timed mastery."""
import mido
import pytest

from piano_teacher import server
from piano_teacher.learner_state import LearnerStateStore, guided_units
from piano_teacher.server import PracticeEngine


@pytest.fixture
def course(tmp_path, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(server.time, 'monotonic', lambda: now[0])
    engines = []

    def create(kind='chords', *, connected=True, reopen=None, path=None):
        if path is None:
            path = tmp_path / f'{kind}-{len(engines)}.mid'
            midi = mido.MidiFile(ticks_per_beat=480)
            track = mido.MidiTrack()
            midi.tracks.append(track)
            track.append(mido.MetaMessage('track_name', name='Right hand'))
            track.append(mido.MetaMessage('set_tempo', tempo=750000))
            track.append(mido.MetaMessage('time_signature', numerator=3 if kind == 'mixed' else 4, denominator=4))
            length = 56 if kind == 'mixed' else 64
            events = []
            if kind == 'sparse':
                notes = [(0, 1, 60), (32, 33, 64), (60, 64, 67)]
            elif kind == 'dense':
                notes = [(i/8, i/8+.1, 60+i%5) for i in range(length*8)]
                notes.append((length-.125, length, 72))
            elif kind == 'melody':
                notes = [(i, i+(.5 if i < length-1 else 1), 60+(0, 2, 4, 5)[i%4]) for i in range(length)]
            else:
                notes = [(i, i+(.5 if i < length-1 else 1), 60+(0, 2, 4, 5)[i%4]+tone)
                         for i in range(length) for tone in (0, 4, 7)]
            if kind == 'mixed':
                events.append((24*480, 0, mido.MetaMessage('time_signature', numerator=4, denominator=4)))
            for begin, end, pitch in notes:
                events.append((round(begin*480), 2, mido.Message('note_on', note=pitch, velocity=80)))
                events.append((round(end*480), 1, mido.Message('note_off', note=pitch, velocity=0)))
            previous = 0
            for tick, _, message in sorted(events, key=lambda event: (event[0], event[1])):
                track.append(message.copy(time=tick-previous))
                previous = tick
            midi.save(path)
        data_dir = reopen if reopen is not None else tmp_path / f'data-{len(engines)}'
        e = PracticeEngine(data_dir, enable_midi=False)
        engines.append(e)
        e.load(str(path))
        if connected:
            e.midi_port = object()
            e.midi_device = 'Learner piano'
        return e, now, path, data_dir

    yield create
    for e in engines:
        e.db.close()


def ack(e):
    state = e.state()
    e.geometry()
    e.control('score_ready', revision=state['revision'])
    return e.state()


def midi(e, now, pitch, down=True, *, at=None):
    now[0] = now[0]+.02 if at is None else at
    e._receive(mido.Message('note_on' if down else 'note_off', note=pitch, velocity=80 if down else 0))


def find_notes(e, now, *, wrong_first=False):
    if wrong_first:
        midi(e, now, 90)
        midi(e, now, 90, False)
        assert e.state()['teaching']['hint_visible']
    while e.state()['phase'] == 'guided_wait':
        expected = e.state()['teaching']['expected_notes']
        for note in expected:
            midi(e, now, note['pitch'])
        for note in expected:
            midi(e, now, note['pitch'], False)
    return e.state()


def perform_notes(e, now, *, until=None):
    phrase = e.plan.active_phrase
    events = []
    for note in phrase.notes:
        beat = note.start-phrase.start
        if beat < e.play_from_beat or (until is not None and beat >= until):
            continue
        for endpoint, down in ((note.start, True), (min(note.end, phrase.end), False)):
            at = e.run_at+(endpoint-phrase.start-e.play_from_beat)*60/e.plan.bpm+.02
            events.append((at, note.pitch, down))
    for at, pitch, down in sorted(events):
        midi(e, now, pitch, down, at=at)
        e.state()


def take(e, now):
    perform_notes(e, now)
    now[0] = e.run_at+(e.plan.active_phrase.end-e.plan.active_phrase.start-e.play_from_beat)*60/e.plan.bpm+.23
    return e.state()


def advance(e, now):
    now[0] = e.next_at+.01
    state = e.state()
    return ack(e) if state['phase'] == 'loading' else state


def begin(e):
    e.control('tempo', bpm=80)
    e.control('learn')
    return ack(e)


def fail_second_unit(e, now):
    perform_notes(e, now, until=8)
    now[0] = e.run_at+16*60/e.plan.bpm+.03
    state = e.state()
    assert state['phase'] == 'recovering'
    return state


def test_sixteen_bar_import_prepares_each_source_idea_then_combines_them_in_rhythm(course):
    e, now, _, _ = course()
    state = begin(e)
    assert e.plan.piece.bar_boundaries[-1] == 64
    assert state['learner']['course_guided']
    assert state['learner']['prepared_units'] == 0 and state['learner']['total_units'] == 4
    visited = []
    for index, bars in enumerate(((1, 2), (3, 4), (5, 6), (7, 8))):
        visited.append((state['first_bar'], state['last_bar']))
        complete = find_notes(e, now, wrong_first=index == 0)
        assert complete['phase'] == 'guided_complete'
        assert complete['learner']['prepared_units'] == index+1
        assert complete['teaching']['has_more_units'] == (index < 3)
        assert not e.plan.mastered and e.plan.streak == 0
        e.control('learn_next')
        waiting = e.state()
        assert waiting['phase'] == 'loading'
        state = ack(e)
    assert visited == [(1, 2), (3, 4), (5, 6), (7, 8)]
    assert state['mode'] == 'practice' and state['phase'] == 'count_in'
    assert state['first_bar'] == 1 and state['last_bar'] == 8 and state['required_notes'] == 32
    assert len(e.plan.piece.notes) == 192 and not e.plan.mastered


def test_saved_guided_unit_resumes_after_reopening_real_import_without_mastery(course):
    e, now, path, data_dir = course()
    begin(e)
    find_notes(e, now)
    e.control('learn_next')
    second = ack(e)
    assert second['first_bar'] == 3
    midi(e, now, second['teaching']['expected_notes'][0]['pitch'])
    e.control('stop')
    reopened, _, _, _ = course(path=path, reopen=data_dir)
    reopened.control('learn')
    state = ack(reopened)
    assert state['first_bar'] == 3 and state['last_bar'] == 4
    assert state['learner']['prepared_units'] == 1
    assert state['teaching']['target_index'] == 0  # Resume source idea, never guessed partial answers.
    assert state['bpm'] == state['target_bpm'] == 80 and not reopened.plan.mastered


def test_explicit_rhythm_choice_does_not_claim_unprepared_units(course):
    e, _, _, _ = course()
    begin(e)
    e.control('practice')
    state = ack(e)
    assert state['mode'] == 'practice' and state['phase'] == 'count_in'
    assert state['learner']['prepared_units'] == 0 and not e.plan.mastered


def test_three_real_clean_full_takes_advance_guided_course_to_next_variant_learn(course):
    e, now, _, _ = course()
    begin(e)
    first_stage = e.plan.identity
    e.control('practice')
    ack(e)
    for streak in (1, 2, 3):
        feedback = take(e, now)
        assert f'Clean pass {streak}/3' in feedback['next_action']
        assert first_stage not in e.plan.mastered
        if streak < 3:
            assert advance(e, now)['phase'] == 'count_in'
    next_stage = advance(e, now)
    assert e.plan.mastered[first_stage] == 80
    assert next_stage['mode'] == 'learn' and next_stage['phase'] == 'guided_wait'
    assert next_stage['lesson_level'] == 'outline' and next_stage['first_bar'] == 1 and next_stage['last_bar'] == 2
    assert next_stage['required_notes'] == 16 and next_stage['learner']['prepared_units'] == 0
    assert next_stage['target_bpm'] == 80


def test_optional_original_placement_and_skip_status_never_invent_mastery(course):
    e, _, _, _ = course()
    state = begin(e)
    assert state['placement_available'] and state['skip_available']
    skeleton = e.plan.identity
    e.control('place_original')
    state = ack(e)
    assert state['lesson_level'] == 'original' and state['mode'] == 'learn'
    assert not state['placement_available'] and not e.plan.mastered
    steps = e.lesson_overview()['steps']
    first_hand = [step for step in steps if step['exercise'] == 1 and step['hand'] == 'right']
    assert [step['skip_status'] for step in first_hand] == ['placed', 'placed', 'active']
    assert all(not step['completed'] for step in first_hand)
    e.control('skip_stage', reason='Student chose the next musical section')
    assert not e.plan.mastered
    assert next(step for step in e.lesson_overview()['steps'] if step['key'] == skeleton)['skip_status'] == 'placed'
    assert next(step for step in e.lesson_overview()['steps'] if step['level'] == 'original' and step['exercise'] == 1)['skip_status'] == 'skipped'


def test_saved_trouble_is_visible_across_stages_and_can_revisit_exact_source_unit(course):
    e, now, _, _ = course()
    begin(e)
    stage = e.plan.identity
    e.control('practice')
    ack(e)
    fail_second_unit(e, now)
    trouble = e.state()['learner']['trouble_units'][0]
    assert trouble['first_bar'] == 3 and trouble['last_bar'] == 4
    assert trouble['failures'] == 1 and trouble['errors'] == 8
    assert trouble['pitches'] == [67, 69, 71, 72]
    e.control('skip_stage', reason='Try the next level before revisiting')
    assert e.plan.identity != stage
    spot = e.lesson_overview()['trouble_spots'][0]
    assert spot['stage_key'] == stage and spot['start_beat'] == 8
    e.control('revisit_trouble', stage_key=stage, start_beat=8)
    state = ack(e)
    assert e.plan.identity == stage and state['mode'] == 'learn'
    assert state['first_bar'] == 3 and state['last_bar'] == 4
    assert state['required_notes'] == 8 and state['guided_recovery']
    assert not e.plan.mastered


def test_clean_full_take_resolves_saved_trouble_after_real_improvement(course):
    e, now, _, _ = course()
    begin(e)
    e.control('practice')
    ack(e)
    fail_second_unit(e, now)
    assert e.lesson_overview()['trouble_spots']
    e.control('practice')
    ack(e)
    assert take(e, now)['phase'] == 'feedback'
    advance(e, now)
    assert not e.lesson_overview()['trouble_spots']
    assert not e.plan.mastered and e.plan.streak == 0  # Still restoring the selected tempo.


@pytest.mark.parametrize('stage,start', [('unknown', 8), (None, 8), ('current', 999), ('current', '8'), ('current', float('nan'))])
def test_invalid_trouble_revisit_does_not_stop_current_attempt(course, stage, start):
    e, now, _, _ = course()
    begin(e)
    key = e.plan.identity
    e.control('practice')
    ack(e)
    fail_second_unit(e, now)
    e.control('practice')
    before = ack(e)
    with pytest.raises(ValueError):
        e.control('revisit_trouble', stage_key=key if stage == 'current' else stage, start_beat=start)
    after = e.state()
    assert after['phase'] == before['phase'] and after['running']
    assert after['revision'] == before['revision'] and e.plan.identity == key


def test_saved_trouble_with_obsolete_source_ids_is_rejected_before_navigation(course):
    e, _, _, _ = course()
    begin(e)
    unit = guided_units(e.plan.active_variant, e.plan.piece.bar_boundaries)[0]
    corrupt = dict(unit, source_indices=[999], required_notes=1)
    LearnerStateStore(e.db).record_trouble(e.fingerprint, e.plan.identity, corrupt, errors=5, pitches=[60])
    before = e.state()
    with pytest.raises(ValueError):
        e.control('revisit_trouble', stage_key=e.plan.identity, start_beat=0)
    after = e.state()
    assert after['revision'] == before['revision'] and after['phase'] == before['phase']


def test_explicit_skips_arrive_at_uninterrupted_original_whole_piece_perform(course):
    e, _, _, _ = course()
    begin(e)
    while e.state()['kind'] != 'perform':
        assert e.state()['skip_available']
        e.control('skip_stage', reason='Student chose the next section without mastery')
    final = e.state()
    assert not final['skip_available'] and final['mode'] == 'perform'
    assert final['lesson_level'] == 'original' and final['hand'] == 'both'
    assert e.plan.active_phrase.notes == e.plan.piece.notes
    assert final['duration_beats'] == 64 and final['required_notes'] == 192
    assert not e.plan.mastered
    assert ack(e)['phase'] == 'count_in'


@pytest.mark.parametrize('kind', ('melody', 'mixed', 'sparse', 'dense', 'chords'))
def test_arbitrary_sixteen_bar_material_gets_source_units_and_retains_original_whole_coverage(course, kind):
    e, _, _, _ = course(kind)
    state = begin(e)
    units = guided_units(e.plan.active_variant, e.plan.piece.bar_boundaries)
    assert state['learner']['total_units'] == len(units)
    assert state['learner']['current_unit'] == units[0]
    assert state['required_notes'] == units[0]['required_notes']
    assert not e.plan.mastered
    e.control('perform', scope='whole')
    whole = e.state()
    assert e.plan.active_phrase.notes == e.plan.piece.notes
    assert whole['last_bar'] == 16
    assert whole['duration_beats'] == (56 if kind == 'mixed' else 64)


def test_no_piano_cannot_prepare_units_or_persist_completion(course):
    e, now, _, _ = course(connected=False)
    state = begin(e)
    assert state['phase'] == 'disconnected' and state['learner']['prepared_units'] == 0
    for pitch in (67, 69, 71, 72):
        midi(e, now, pitch)
        midi(e, now, pitch, False)
    assert e.state()['learner']['prepared_units'] == 0
    assert not e.plan.mastered and not e.lesson_overview()['trouble_spots']


def test_explicit_learn_revisits_notes_after_all_ideas_prepared_instead_of_starting_time(course):
    e, now, _, _ = course()
    begin(e)
    for _ in range(4):
        find_notes(e, now)
        e.control('learn_next')
        ack(e)
    assert e.state()['mode'] == 'practice'
    e.control('learn')
    learned = ack(e)
    assert learned['mode'] == 'learn' and learned['phase'] == 'guided_wait'
    assert learned['first_bar'] == 1 and learned['last_bar'] == 2
    assert learned['learner']['prepared_units'] == 4 and not e.plan.mastered


def test_perform_weakness_persists_source_unit_for_later_guided_revisit_without_mastery(course):
    e, now, _, _ = course()
    e.control('perform')
    ack(e)
    now[0] = e.run_at+(e.plan.active_phrase.end-e.plan.active_phrase.start)*60/e.plan.bpm+.23
    review = e.state()
    assert review['phase'] == 'performance_complete'
    spots = e.lesson_overview()['trouble_spots']
    assert len(spots) == 4 and all(spot['errors'] == 8 for spot in spots)
    spot = spots[0]
    e.control('revisit_trouble', stage_key=spot['stage_key'], start_beat=spot['start_beat'])
    learned = ack(e)
    assert learned['phase'] == 'guided_wait' and learned['guided_recovery']
    assert learned['first_bar'] == spot['first_bar'] and not e.plan.mastered


def test_legacy_timed_recovery_does_not_enable_guided_course_progression(course):
    e, now, _, _ = course()
    e.control('tempo', bpm=80)
    e.start()
    fail_second_unit(e, now)
    advance(e, now)
    now[0] = e.run_at+(16-e.play_from_beat)*60/e.plan.bpm+.03
    assert e.state()['guided_recovery']
    assert advance(e, now)['mode'] == 'learn'
    assert not e.state()['learner']['course_guided']
    find_notes(e, now)
    e.control('practice')
    ack(e)
    e.control('tempo', bpm=80)
    e.control('practice')
    ack(e)
    for _ in range(3):
        take(e, now)
        state = advance(e, now)
    assert state['lesson_level'] == 'outline' and state['mode'] == 'practice'
    assert state['phase'] == 'count_in'


def test_actual_237_bar_import_performs_every_original_event_and_no_input_cannot_score(tmp_path, monkeypatch):
    from pathlib import Path
    source = Path('/home/tom/Music/Piano Teacher/Merry-Go-Round-of-Life.midi')
    if not source.is_file():
        pytest.skip('The local 237-bar user import is unavailable')
    now = [100.0]
    monkeypatch.setattr(server.time, 'monotonic', lambda: now[0])
    e = PracticeEngine(tmp_path, enable_midi=False)
    try:
        e.load(str(source))
        assert len(e.plan.piece.notes) == 2346
        e.control('perform', scope='whole')
        state = e.state()
        assert state['first_bar'] == 1 and state['last_bar'] == 237
        assert state['required_notes'] == 2346
        assert e.plan.active_phrase.notes == e.plan.piece.notes
        e.control('score_ready', revision=state['revision'])
        now[0] = e.run_at+state['duration_beats']*60/e.plan.bpm+.23
        preview = e.state()
        assert preview['phase'] == 'ready' and preview['performance_summary'] is None
        assert not e.plan.mastered and e.plan.streak == 0
    finally:
        e.db.close()


def test_cross_stage_trouble_revisit_preserves_the_students_current_selected_tempo(course):
    e, now, _, _ = course()
    begin(e)
    original = e.plan.identity
    e.control('practice')
    ack(e)
    fail_second_unit(e, now)
    e.control('skip_stage', reason='Try the fuller notes first')
    e.control('tempo', bpm=60)
    assert e.state()['bpm'] == e.state()['target_bpm'] == 60
    e.control('revisit_trouble', stage_key=original, start_beat=8)
    revisited = ack(e)
    assert revisited['bpm'] == revisited['target_bpm'] == 60


def test_obsolete_trouble_history_is_retained_but_only_current_source_spots_are_published(course):
    e, _, _, _ = course()
    begin(e)
    first, second, *_ = guided_units(e.plan.active_variant, e.plan.piece.bar_boundaries)
    store = LearnerStateStore(e.db)
    stage = e.plan.identity
    store.record_trouble(e.fingerprint, 'obsolete-course-stage', first, errors=5, pitches=[60])
    store.record_trouble(e.fingerprint, stage, dict(first, source_indices=[999], required_notes=1),
                         errors=5, pitches=[60])
    store.record_trouble(e.fingerprint, stage, second, errors=6, pitches=[67])
    published = e.lesson_overview()['trouble_spots']
    assert len(published) == 1 and published[0]['stage_key'] == stage
    assert published[0]['source_indices'] == second['source_indices']
    assert e.state()['learner']['trouble_units'] == [
        {key: value for key, value in published[0].items() if key != 'stage_key'}]
    assert len(store.trouble_for_piece(e.fingerprint)) == 3
    before = e.state()
    for key, start in [('obsolete-course-stage', 0), (stage, 0)]:
        with pytest.raises(ValueError):
            e.control('revisit_trouble', stage_key=key, start_beat=start)
        assert e.state()['revision'] == before['revision'] and e.state()['phase'] == before['phase']


@pytest.mark.parametrize('all_prepared', (False, True))
def test_tempo_setting_rebinds_current_guided_idea_without_starting_time(course, all_prepared):
    e, now, _, _ = course()
    begin(e)
    for index in range(4 if all_prepared else 2):
        if index:
            e.control('learn_next')
            ack(e)
        find_notes(e, now)
    before = e.state()
    assert before['mode'] == 'learn' and before['phase'] == 'guided_complete'
    first, last = before['first_bar'], before['last_bar']
    e.control('tempo', bpm=60)
    updated = ack(e)
    assert updated['mode'] == 'learn' and updated['phase'] == 'guided_wait'
    assert (updated['first_bar'], updated['last_bar']) == (first, last)
    assert updated['bpm'] == updated['target_bpm'] == 60
    assert not updated['running'] and updated['clock_beat'] == 0
    assert not e.plan.mastered


def test_tempo_during_guided_recovery_keeps_failed_fragment_and_rhythm_return_with_fresh_keys(course):
    e, now, _, _ = course()
    e.control('tempo', bpm=80)
    e.start()
    fail_second_unit(e, now)
    advance(e, now)
    now[0] = e.run_at+(16-e.play_from_beat)*60/e.plan.bpm+.03
    assert e.state()['guided_recovery']
    recovered = advance(e, now)
    assert recovered['mode'] == 'learn' and recovered['first_bar'] == 3
    pitch = recovered['teaching']['expected_notes'][0]['pitch']
    midi(e, now, pitch)  # This key remains physically held through the tempo change.
    e.control('tempo', bpm=60)
    changed = ack(e)
    assert changed['guided_recovery'] and changed['first_bar'] == 3 and changed['last_bar'] == 4
    assert changed['bpm'] == changed['target_bpm'] == 60
    midi(e, now, pitch)
    assert e.state()['teaching']['target_index'] == 0
    midi(e, now, pitch, False)
    midi(e, now, pitch)
    midi(e, now, pitch, False)
    find_notes(e, now)
    e.control('practice')
    ready = ack(e)
    assert ready['phase'] == 'count_in' and ready['play_from_beat'] == 8
    assert ready['bpm'] == ready['target_bpm'] == 60
    assert not e.plan.mastered and e.plan.streak == 0


def test_explicit_learn_on_whole_piece_perform_enters_static_original_source_fragment(course):
    e, _, _, _ = course()
    e.control('perform', scope='whole')
    performance = e.state()
    assert performance['mode'] == 'perform' and performance['kind'] == 'perform'
    original_notes = e.plan.active_phrase.notes
    e.control('learn')
    loading = e.state()
    assert loading['mode'] == 'learn' and loading['phase'] == 'loading'
    assert loading['revision'] > performance['revision']
    e.control('score_ready', revision=performance['revision'])
    assert e.state()['phase'] == 'loading'
    learned = ack(e)
    assert learned['mode'] == 'learn' and learned['phase'] == 'guided_wait'
    assert learned['kind'] == 'perform' and learned['lesson_level'] == 'original'
    assert learned['last_bar']-learned['first_bar'] < 2
    assert e.plan.active_phrase.notes == original_notes == e.plan.piece.notes
    assert learned['required_notes'] == 24
    source_ids = {f'{e.plan.identity}:{index}' for index in e.plan.active_variant.source_indices}
    assert all(note['id'] in source_ids for note in learned['teaching']['expected_notes'])
    assert [note['pitch'] for note in learned['teaching']['expected_notes']] == [60, 64, 67]
    assert not learned['running'] and learned['clock_beat'] == 0
    assert e.recorder is None and e.pending_result is None and not e.auto and not e.plan.mastered
