"""Completed-take evidence retains the performed tempo across slower retries."""
from __future__ import annotations

import sqlite3

import pytest

from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.practice import Assessment, NoteAssessment
from piano_teacher.server import PracticeEngine


def _seal_completed(engine, result):
    engine.measurement.seal(engine.recorder.presses, state="completed",
                            reason="full_passage", result=result,
                            eligible=engine.plan.bpm >= engine.plan.target_bpm)


@pytest.mark.parametrize("strategy,restart", [
    ("slow-practice", 0.0),
    ("micro-loop", 8.0),
])
@pytest.mark.parametrize("interrupt_commit", [False, True])
def test_completed_take_history_uses_performed_bpm_before_retry_slowdown(
        tmp_path, strategy, restart, interrupt_commit):
    notes = tuple(Note(float(beat), beat + .5, 60 + index, 0, 0,
                       "right", f"source-{index}")
                  for index, beat in enumerate((0, 4, 8)))
    piece = Piece("Assessed tempo", 100, notes,
                  (Phrase(1, 1, 3, 0, 12, notes),),
                  bar_boundaries=(0, 4, 8, 12),
                  time_signatures=((0, 4, 4),))
    engine = PracticeEngine(tmp_path, enable_midi=False)
    try:
        engine.set_preferences(mistake_response_strategy=strategy)
        engine.plan = LearningPlan(piece, exercise_strategy="source-progression")
        engine.plan.set_bpm(100)
        engine.fingerprint = "performed-tempo-source"
        engine.midi.port = object()
        engine.start()
        result = Assessment(tuple(NoteAssessment(note, "missed")
                                  for note in notes), 0)
        end = engine.visual_transport.run_at + 7.4

        _seal_completed(engine, result)
        engine._finish_full_passage(result, 12.0, 7.2, end)
        assert engine.plan.bpm == 90
        assert engine.visual_transport.pending_rewind == restart
        if interrupt_commit:
            engine.db.execute("""CREATE TRIGGER reject_progress_write
                BEFORE INSERT ON strategy_sessions
                BEGIN SELECT RAISE(ABORT, 'interrupted progress write'); END""")
            with pytest.raises(sqlite3.IntegrityError, match="interrupted"):
                engine._commit_pending()
            assert engine.pending_result is result
            assert engine.db.execute(
                "SELECT count(*) FROM learning_assessments").fetchone()[0] == 0
            engine.db.execute("DROP TRIGGER reject_progress_write")
        engine._commit_pending()

        assert engine.db.execute(
            "SELECT bpm FROM learning_assessments").fetchall() == [(100.0,)]
        assert engine.db.execute(
            "SELECT bpm FROM strategy_sessions").fetchall() == [(90,)]
        assert engine.plan.bpm == 90
        assert not engine.plan.mastered
    finally:
        engine.db.close()


@pytest.mark.parametrize("command", [
    {"action": "stop"},
    {"action": "tempo", "bpm": 80},
    {"action": "select_step", "number": 2},
    {"action": "learn"},
])
def test_cancelled_feedback_retains_evidence_without_attaching_old_tempo_to_later_take(tmp_path, command):
    notes = tuple(Note(index * .25, (index + 1) * .25, 60 + index, 0, 0,
                       "right", f"source-{index}") for index in range(16))
    piece = Piece("New take tempo", 100, notes,
                  (Phrase(1, 1, 1, 0, 4, notes),),
                  bar_boundaries=(0, 4))
    engine = PracticeEngine(tmp_path, enable_midi=False)
    try:
        engine.set_preferences(mistake_response_strategy="slow-practice")
        engine.plan = LearningPlan(piece, exercise_strategy="source-progression")
        engine.plan.set_bpm(100)
        engine.fingerprint = "cancelled-feedback-source"
        engine.midi.port = object()
        engine.start()
        result = Assessment(tuple(NoteAssessment(n, "missed")
                                  for n in engine.plan.active_phrase.notes), 0)
        _seal_completed(engine, result)
        engine._finish_full_passage(
            result, 4.0, 2.4, engine.visual_transport.run_at + 2.6)

        engine.control(**command)
        assert engine.pending_result is None
        engine._commit_pending()
        assert engine.db.execute(
            "SELECT bpm,mastery_eligible FROM learning_assessments").fetchall() == [(100.0, 0)]
        assert engine.plan.streak == 0 and not engine.plan.mastered

        engine.control("tempo", bpm=80)
        if engine.mode == "learn":
            engine.control("practice")
        engine.start()
        selected_notes = engine.plan.active_phrase.notes
        result = Assessment(tuple(NoteAssessment(n, "missed")
                                  for n in selected_notes), 0)
        _seal_completed(engine, result)
        engine._finish_full_passage(
            result, 4.0, 3.0, engine.visual_transport.run_at + 3.2)
        engine._commit_pending()
        assert engine.db.execute(
            "SELECT bpm FROM learning_assessments ORDER BY id").fetchall() == [(100.0,), (80.0,)]
        assert engine.plan.bpm == 72
    finally:
        engine.db.close()
