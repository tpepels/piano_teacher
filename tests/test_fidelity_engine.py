"""Production engine must preserve exact musical identity and saved progress."""
from dataclasses import replace
import mido

from piano_teacher.application import score_artifacts
from piano_teacher import server
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase
from piano_teacher.server import PracticeEngine


def test_full_piece_preserves_explicit_introduction_rest_measures(tmp_path):
    path = tmp_path/'Introduction.musicxml'
    path.write_text('''<score-partwise version="4.0"><part-list><score-part id="P1"><part-name>Right hand</part-name></score-part></part-list>
<part id="P1"><measure number="1"><attributes><divisions>1</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes><note><rest measure="yes"/><duration>4</duration></note></measure>
<measure number="2"><note><rest measure="yes"/><duration>4</duration></note></measure>
<measure number="3"><note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>whole</type></note></measure></part></score-partwise>''')
    piece, _ = server.import_piece(path)
    plan = LearningPlan(piece)
    assert piece.bar_boundaries == (0, 4, 8, 12)
    assert plan.exercises[0].phrase.start == 8
    full = plan.exercises[-1]
    assert full.kind == 'perform'
    assert (full.phrase.start, full.phrase.end) == (0, 12)
    assert full.phrase.notes == piece.notes


def write_unisons(path):
    midi = mido.MidiFile(ticks_per_beat=480)
    for name in ('Right hand', 'Left hand'):
        track = mido.MidiTrack([mido.MetaMessage('track_name', name=name)])
        midi.tracks.append(track)
        for pitch in (60, 62, 64, 65):
            track.extend((mido.Message('note_on', note=pitch, velocity=80),
                          mido.Message('note_off', note=pitch, time=240),
                          mido.MetaMessage('marker', text='rest', time=240)))
    midi.save(path)


def test_guided_simultaneous_cross_hand_unisons_use_distinct_real_noteheads(tmp_path):
    path = tmp_path/'Two hands on the same pitches.mid'
    write_unisons(path)
    e = PracticeEngine(tmp_path/'data', enable_midi=False)
    try:
        e.load(str(path))
        e.plan.set_hand('both')
        e.midi.port = object()
        e.midi.device = 'Fixture piano'
        e.control('learn')
        e.geometry()
        e.control('score_ready', revision=e.score_revision)
        state = e.state()
        marks = state['feedback_marks']
        assert len(marks) == 2
        assert len({mark['id'] for mark in marks}) == 2, 'Each hand needs its own exact engraved attack'
        assert len({mark['y'] for mark in marks}) == 2, 'Unison feedback must remain on the intended staff'
        targets = state['teaching']['expected_notes']
        assert {mark['source_id'] for mark in marks} == {target['source_id'] for target in targets}
        assert all(mark['is_attack'] for mark in marks)
    finally:
        e.db.close()


def test_piece_key_and_clef_metadata_reach_active_lesson_compiler(tmp_path, monkeypatch):
    path = tmp_path/'Explicit metadata.musicxml'
    path.write_text('''<?xml version="1.0"?>
<score-partwise version="4.0"><part-list><score-part id="P1"><part-name>Left hand</part-name></score-part></part-list>
<part id="P1"><measure number="1"><attributes><divisions>1</divisions><key><fifths>-5</fifths><mode>major</mode></key><time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes>
<note><pitch><step>D</step><alter>-1</alter><octave>6</octave></pitch><duration>4</duration><type>whole</type></note></measure></part></score-partwise>''')
    captured = {}
    original = score_artifacts.build_lesson_score
    def record(phrase, **kwargs):
        captured.update(kwargs)
        return original(phrase, **kwargs)
    monkeypatch.setattr(score_artifacts, 'build_lesson_score', record)
    # XML remains a supported internal source; desktop selection is MIDI only.
    piece, _ = server.import_piece(path)
    selected = score_artifacts.ScoreSelection(piece, piece.phrases[0], 'left',
        'source-metadata', 1, path.name)
    from piano_teacher.preprocessing_cache import PreprocessingCache
    artifacts = score_artifacts.ScoreArtifacts(PreprocessingCache(tmp_path/'metadata-data'))
    geometry = artifacts.geometry(selected)
    assert captured.get('key_signatures'), 'Source keys must reach the actual lesson compiler'
    assert captured.get('clef_changes'), 'Source clefs must reach the actual lesson compiler'
    assert captured['key_signatures'] == piece.key_signatures
    assert captured['clef_changes'] == piece.clef_changes
    assert geometry['staff_clefs']['left']['sign'] == 'G'


def test_ordinary_midi_identity_metadata_does_not_invalidate_saved_course_progress(tmp_path):
    path = tmp_path/'Existing progress.mid'
    write_unisons(path)
    data = tmp_path/'saved-data'
    e = PracticeEngine(data, enable_midi=False)
    try:
        e.load(str(path))
        piece = e.plan.piece
        old_notes = tuple(Note(n.start,n.end,n.pitch,n.track,n.channel,n.hand,n.source_id) for n in piece.notes)
        old_by_object = {id(note): old for note,old in zip(piece.notes,old_notes)}
        old_phrases = tuple(replace(phrase, notes=tuple(old_by_object[id(n)] for n in phrase.notes))
                            for phrase in piece.phrases)
        legacy = LearningPlan(replace(piece, notes=old_notes, phrases=old_phrases),
                              exercise_strategy=e.library.settings['exercise_strategy'])
        assert [step.key for step in legacy.lesson_steps] == [step.key for step in e.plan.lesson_steps]
        e.plan = legacy
        e.plan.set_bpm(88)
        e.plan.streak = 2
        key = e.plan.identity
        e.plan.mastered[key] = 80
        e._save()
    finally:
        e.db.close()
    reopened = PracticeEngine(data, enable_midi=False)
    try:
        reopened.load(str(path))
        assert reopened.plan.identity == key
        assert reopened.plan.bpm == reopened.plan.target_bpm == 88
        assert reopened.plan.streak == 2
        assert reopened.plan.mastered[key] == 80
    finally:
        reopened.db.close()


def test_corrected_pickup_course_keeps_history_and_resets_incompatible_streak(tmp_path):
    path = tmp_path/'Pickup progress.mid'
    midi = mido.MidiFile(ticks_per_beat=480)
    midi.tracks.append(mido.MidiTrack([
        mido.MetaMessage('track_name', name='Right hand'),
        mido.MetaMessage('time_signature', numerator=1, denominator=4),
        mido.Message('note_on', note=60, velocity=80),
        mido.Message('note_off', note=60, time=480),
        mido.MetaMessage('time_signature', numerator=4, denominator=4),
        mido.Message('note_on', note=62, velocity=80),
        mido.Message('note_off', note=62, time=1920)]))
    midi.save(path)
    data = tmp_path/'pickup-progress-data'
    old = PracticeEngine(data, enable_midi=False)
    try:
        old.load(str(path))
        piece = old.plan.piece
        # Reproduce the old inferred 4/4 grid for the same unchanged source file.
        old_notes = tuple(Note(n.start,n.end,n.pitch,n.track,n.channel,n.hand,n.source_id) for n in piece.notes)
        legacy = replace(piece, notes=old_notes, bar_boundaries=(0,4,8),
                         phrases=(Phrase(1,1,2,0,8,old_notes),))
        old.plan = LearningPlan(legacy, exercise_strategy=old.library.settings['exercise_strategy'])
        old.plan.set_bpm(88)
        old.plan.streak = 2
        old_key = old.plan.identity
        old.plan.mastered[old_key] = 80
        old._save()
    finally:
        old.db.close()
    reopened = PracticeEngine(data, enable_midi=False)
    try:
        reopened.load(str(path))
        assert reopened.plan.piece.bar_boundaries == (0,1,5)
        assert reopened.plan.identity != old_key
        # The piece-wide target survives; a superseded course row is retained on
        # disk but never executed, so no old tempo, streak or mastery is applied.
        assert reopened.plan.target_bpm == 88 and reopened.plan.bpm != 88
        assert reopened.plan.streak == 0
        assert old_key not in reopened.plan.mastered
        kept = reopened.progress.db.execute(
            "SELECT bpm FROM mastery WHERE fingerprint=? AND exercise=?",
            (reopened.fingerprint, old_key)).fetchone()
        assert kept == (80,)
        assert reopened.plan.exercise.phrase.first_bar == 1
        assert reopened.plan.exercise.phrase.last_bar == 2
    finally:
        reopened.db.close()
