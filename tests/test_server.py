from pathlib import Path
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.server import PracticeEngine


def fixture_piece():
    notes = (Note(0, 1, 60, 0, 0, 'right'), Note(1, 2, 62, 0, 0, 'right'))
    phrase = Phrase(1, 1, 2, 0, 8, notes)
    return Piece('Test', 100, notes, (phrase,))


def test_backend_state_and_actions(tmp_path):
    engine=PracticeEngine(tmp_path,enable_midi=False)
    engine.plan=LearningPlan(fixture_piece())
    engine.fingerprint='testhash'
    assert engine.state()['bpm']==40
    engine.control('tempo',bpm=80)
    assert engine.state()['bpm']==80
    engine.control('hand',hand='both')
    assert engine.state()['hand']=='both'
    engine.control('start')
    assert engine.state()['phase']=='count_in'
    engine.control('stop')
    assert not engine.state()['running']
    engine.db.close()


def test_progress_persists(tmp_path):
    first=PracticeEngine(tmp_path,enable_midi=False)
    first.plan=LearningPlan(fixture_piece())
    first.fingerprint='abc'
    first.plan.set_bpm(70)
    first.plan.mastered['learn:1-2:right']=100
    first._save()
    first.db.close()
    second=PracticeEngine(tmp_path,enable_midi=False)
    second.plan=LearningPlan(fixture_piece())
    second.fingerprint='abc'
    second._restore()
    assert second.plan.bpm==70
    assert second.plan.mastered['learn:1-2:right']==100
    second.db.close()
