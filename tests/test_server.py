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


def test_layout_cached_until_score_revision_changes(tmp_path, monkeypatch):
    """Multiple UI polls/pages must not repeatedly engrave the same exercise."""
    from piano_teacher.score import EngravedScore
    from piano_teacher import server
    engine = PracticeEngine(tmp_path, enable_midi=False)
    engine.plan = LearningPlan(fixture_piece())
    engine.score = object()
    calls = []
    def fake_render(score, first, last, hand, *, total_beats):
        calls.append((first,last,hand,total_beats))
        return EngravedScore(("<svg>page 1</svg>","<svg>page 2</svg>"),
                             {"pages":2,"anchors":[{"beat":0,"x":.1}],"beats":total_beats,
                              "notes":[{"pitch":n.pitch,"beat":n.start-score.phrase.start}
                                       for n in score.phrase.notes]})
    monkeypatch.setattr(server,"render_layout",fake_render)
    assert engine.engraved(0) == "<svg>page 1</svg>"
    assert engine.engraved(1) == "<svg>page 2</svg>"
    assert engine.geometry()["pages"] == 2
    assert calls == [(1,2,"right",8)]
    with __import__('pytest').raises(ValueError,match="Invalid score page"):
        engine.engraved(2)
    engine.control("hand",hand="both")
    assert engine.geometry()["pages"] == 2
    assert calls[-1] == (1,2,"both",8)
    assert len(calls) == 2
    engine.db.close()


def test_playhead_beat_state_at_countin_and_play(tmp_path):
    engine=PracticeEngine(tmp_path,enable_midi=False)
    engine.plan=LearningPlan(fixture_piece())
    engine.control("start")
    state=engine.state()
    assert state["beat"] == 0
    assert state["duration_beats"] == 8
    assert state["phase"] == "count_in"
    engine.run_at=__import__('time').monotonic() - 1.0
    state=engine.state()
    assert state["phase"] == "playing"
    assert 0 < state["beat"] < 8
    engine.db.close()
