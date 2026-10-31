"""The embedded engine advances deadlines without any Godot state polling."""
from __future__ import annotations

from piano_teacher import server
from piano_teacher.inprocess import EngineCommands
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.server import PracticeEngine


def test_preview_repeats_on_worker_ticks_with_no_state_requests(tmp_path, monkeypatch):
    now = [200.0]
    monkeypatch.setattr(server.time, "monotonic", lambda: now[0])
    notes = (Note(0.0, .5, 60, 0, 0, "right"),
             Note(3.0, 3.5, 62, 0, 0, "right"))
    phrase = Phrase(1, 1, 1, 0, 4, notes)
    piece = Piece("Native timer", 80, notes, (phrase,),
                  bar_boundaries=(0, 4), time_signatures=((0, 4, 4),))
    engine = PracticeEngine(tmp_path, enable_midi=False)
    engine.plan = LearningPlan(piece)
    bridge = EngineCommands(engine=engine)
    try:
        engine.start()
        assert engine.preview_only
        initial_transport = engine.transport_id
        initial_run_at = engine.run_at
        source_end = initial_run_at + 4 * 60 / engine.plan.bpm
        now[0] = source_end + .21
        assert bridge.tick() == 20
        assert engine._preview_loop_pending
        deadline = engine.next_at
        assert deadline == source_end + engine.visual_gap_beats*60/engine.plan.bpm
        now[0] = deadline+.12
        assert bridge.tick() == 20
        assert engine.running
        assert engine.transport_id == initial_transport + 1
        assert engine.run_at == deadline
        assert engine.visual_offset_beats == 4 + engine.visual_gap_beats
        # No /state call has happened since the first Start.
    finally:
        engine.db.close()


def test_worker_does_not_advance_while_paused(tmp_path, monkeypatch):
    now = [200.0]
    monkeypatch.setattr(server.time, "monotonic", lambda: now[0])
    notes = (Note(0, .5, 60, 0, 0, "right"),)
    phrase = Phrase(1, 1, 1, 0, 4, notes)
    piece = Piece("Timer pause", 80, notes, (phrase,),
                  bar_boundaries=(0,4), time_signatures=((0,4,4),))
    engine = PracticeEngine(tmp_path, enable_midi=False)
    engine.plan = LearningPlan(piece)
    bridge = EngineCommands(engine=engine)
    try:
        engine.start()
        before = engine.transport_id
        engine.control("pause")
        now[0] += 60
        assert bridge.tick() == 250
        assert engine.transport_id == before
        assert engine.paused
    finally:
        engine.db.close()
