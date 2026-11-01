"""Attempt timing policy has no dependency on PracticeEngine."""
from __future__ import annotations

from piano_teacher.application import attempt_progression as module
from piano_teacher.application.attempt_progression import AttemptProgression, AttemptTick
from piano_teacher.music import Phrase


PHRASE = Phrase(1,1,2,0.0,8.0,())
BOUNDARIES = (0.0,4.0,8.0)


def tick(now: float, *, next_boundary: float = 4.0,
         preview: bool = False, coda: bool = False,
         gap: float = 4.0) -> AttemptTick:
    return AttemptTick(
        phrase=PHRASE,boundaries=BOUNDARIES,now=now,
        score_beat=now-100.0,from_beat=0.0,run_at=100.0,
        next_boundary=next_boundary,review_end=None,preview=preview,
        auto=True,mode="practice",coda=coda,bpm=60.0,gap_beats=gap)


def test_authoritative_tick_caches_source_grid_until_phrase_changes(monkeypatch):
    actual = module.phrase_grid
    calls = []
    def observed(*args):
        calls.append(args)
        return actual(*args)
    monkeypatch.setattr(module,"phrase_grid",observed)
    progression = AttemptProgression()
    assessed = []
    def recover(boundary,grid):
        assessed.append((boundary,grid))
        return None

    boundary = 4.0
    for now in (100.0,102.0,103.0,104.0,105.0,107.9):
        result = progression.inspect(tick(now,next_boundary=boundary),
                                     recover,float)
        boundary = result.next_boundary
        assert result.action == "waiting"
    assert len(calls)==1
    assert boundary==8.0
    assert len(assessed)==1
    finished = progression.inspect(tick(108.2,next_boundary=boundary),
                                   recover,float)
    assert len(calls)==1
    assert len(assessed)==2
    assert finished.action=="complete"
    assert (finished.ending,finished.duration)==(8.0,8.0)

    replacement = Phrase(2,1,2,0.0,8.0,())
    assert progression.grid_for(replacement,BOUNDARIES)==BOUNDARIES
    assert len(calls)==2


def test_coda_defers_recovery_assessment_until_end_of_phrase():
    progression = AttemptProgression()
    assessed = []
    def recover(boundary,grid):
        assessed.append(boundary)
        return None
    before = progression.inspect(tick(104.01,coda=True),recover,float)
    assert before.action=="waiting"
    assert before.next_boundary==4.0
    assert assessed==[]
    at_end = progression.inspect(tick(108.19,coda=True),recover,float)
    assert at_end.action=="waiting"
    assert assessed==[4.0,8.0]


def test_recovery_preempts_attempt_completion():
    progression = AttemptProgression()
    decision = object()
    result = progression.inspect(tick(110.0),
        lambda boundary,grid: decision,float)
    assert result.action=="recovery"
    assert result.recovery is decision
    assert result.next_boundary==4.0


def test_preview_shortens_settlement_without_assessment():
    progression = AttemptProgression()
    def forbidden(_boundary,_grid):
        raise AssertionError("Preview should never grade notes")
    assert progression.inspect(tick(108.04,preview=True,gap=.05),
                               forbidden,float).action=="waiting"
    assert progression.inspect(tick(108.06,preview=True,gap=.05),
                               forbidden,float).action=="complete"


def test_start_preserves_authored_meter_and_absolute_deadline():
    progression = AttemptProgression()
    scheduled = progression.schedule_start(
        phrase=PHRASE,boundaries=BOUNDARIES,
        time_signatures=((0.0,4,4),),bpm=80,
        position=4.0,loop_continuation=False,
        preview=False,now=123.0)
    assert scheduled.from_beat==4.0
    assert scheduled.count_in_meter==(4,4)
    assert scheduled.run_at==123.0+scheduled.count_in_beats*60/80
    assert scheduled.next_boundary_beat==8.0
    continued = progression.schedule_start(
        phrase=PHRASE,boundaries=BOUNDARIES,
        time_signatures=((0.0,4,4),),bpm=80,
        position=0.0,loop_continuation=True,
        preview=True,now=133.0)
    assert continued.run_at==133.0
    assert continued.count_in_beats==0.0
    assert progression._grid is not None


def test_start_and_loop_continuation_share_cached_grid_and_clock(tmp_path,monkeypatch):
    from piano_teacher import server
    from piano_teacher.learning import LearningPlan
    from piano_teacher.music import Note, Piece
    from piano_teacher.server import PracticeEngine
    source = (Note(0.0,.5,60,0,0,"right"),
              Note(4.0,4.5,62,0,0,"right"))
    phrase = Phrase(1,1,2,0.0,8.0,source)
    piece = Piece("Start clock contract",80,source,(phrase,),
                  bar_boundaries=BOUNDARIES,
                  time_signatures=((0.0,4,4),))
    monkeypatch.setattr(server.time,"monotonic",lambda:123.0)
    engine = PracticeEngine(tmp_path,enable_midi=False)
    engine.plan = LearningPlan(piece)
    try:
        engine.start()
        assert engine.preview_only
        assert engine.run_at==123.0+engine.count_in_beats*60/engine.plan.bpm
        first_grid = engine.attempt_progression._grid
        first_transport = engine.transport_id
        engine.start(loop_continuation=True)
        assert engine.attempt_progression._grid is first_grid
        assert engine.transport_id==first_transport+1
        assert engine.run_at==123.0
        assert engine.count_in_beats==0.0
        assert not engine.auto
    finally:
        engine.db.close()
