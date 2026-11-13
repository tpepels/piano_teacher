"""Assessments must not partially commit adaptation, mastery or replay credit."""
from __future__ import annotations

import sqlite3

import pytest

from scripts.smoke_phase0 import make_fixture
from piano_teacher.learning import LearningPlan
from piano_teacher.music import load_midi
from piano_teacher.practice import Assessment, NoteAssessment
from piano_teacher.server import PracticeEngine
from piano_teacher.sqlite_transaction import sqlite_atomic


def _engine(tmp_path):
    source = tmp_path / "assessed.mid"
    make_fixture(source)
    piece = load_midi(source)
    engine = PracticeEngine(tmp_path / "app", enable_midi=False)
    engine.plan = LearningPlan(piece, exercise_strategy="coda-fukuda-midi")
    engine.plan.variant_index = len(engine.plan.variants) - 1
    engine.fingerprint = "atomic-graded-midi"
    assert engine.plan.active_variant.level == "original"
    assert engine.plan.accepts_performance_feedback
    engine.auto = True
    return engine


def _result(engine, status):
    notes = engine.plan.active_phrase.notes
    if engine.plan.hand != "both":
        notes = tuple(n for n in notes if n.hand == engine.plan.hand)
    assert notes and len({n.source_id for n in notes}) == len(notes)
    return Assessment(tuple(NoteAssessment(n, status) for n in notes), 0)


def _pending(engine, status):
    """Seal the same exposure that the production commit will settle."""
    engine.midi.port = object()
    engine.start()
    result = _result(engine, status)
    engine.measurement.seal(engine.recorder.presses, state="completed",
                            reason="full_passage", result=result,
                            eligible=engine.plan.bpm >= engine.plan.target_bpm)
    engine.pending_result = result
    engine._pending_assessed_bpm = engine.plan.bpm
    return result


def _durable_counts(engine):
    return tuple(engine.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        for table in ("learning_assessments", "learning_attempt_details",
                      "learning_decisions", "learning_outcomes", "learning_events", "fukuda_mistakes",
                      "strategy_sessions", "sessions", "stage_tempos", "mastery"))


def test_nested_savepoints_do_not_commit_their_enclosing_transaction():
    db = sqlite3.connect(":memory:")
    try:
        db.execute("CREATE TABLE notes (id INTEGER)")
        with pytest.raises(RuntimeError, match="abort"):
            with sqlite_atomic(db):
                db.execute("INSERT INTO notes VALUES (1)")
                with sqlite_atomic(db):
                    db.execute("INSERT INTO notes VALUES (2)")
                assert db.execute("SELECT count(*) FROM notes").fetchone()[0] == 2
                raise RuntimeError("abort")
        assert db.execute("SELECT count(*) FROM notes").fetchone()[0] == 0
        with sqlite_atomic(db):
            db.execute("INSERT INTO notes VALUES (3)")
        assert db.execute("SELECT id FROM notes").fetchall() == [(3,)]
    finally:
        db.close()


def test_history_failure_preserves_pending_take_and_durable_state(
        tmp_path, monkeypatch):
    engine = _engine(tmp_path)
    try:
        result = _pending(engine, "correct")
        before = _durable_counts(engine)
        stage, streak = engine.plan.identity, engine.plan.streak
        observed = engine.measurement.persist

        def fail_after_observe(*args, **kwargs):
            observed(*args, **kwargs)
            raise RuntimeError("history write failure")

        monkeypatch.setattr(engine.measurement, "persist", fail_after_observe)
        with pytest.raises(RuntimeError, match="history write failure"):
            engine._commit_pending()
        assert engine.pending_result is result
        assert engine.plan.identity == stage and engine.plan.streak == streak
        assert _durable_counts(engine) == before
        monkeypatch.delattr(engine.measurement, "persist")
        engine._commit_pending()
        assert engine.pending_result is None
        assert engine.db.execute("SELECT count(*) FROM learning_assessments").fetchone()[0] == 1
    finally:
        engine.db.close()


def test_fukuda_write_failure_restores_existing_source_mistake(
        tmp_path, monkeypatch):
    engine = _engine(tmp_path)
    try:
        bad = _result(engine, "wrong")
        engine.fukuda_mistakes.observe(engine.fingerprint, bad)
        _pending(engine, "correct")
        before = _durable_counts(engine)
        pending = engine.pending_result
        stage, streak = engine.plan.identity, engine.plan.streak
        observed = engine.fukuda_mistakes.observe

        def fail_after_fukuda(*args, **kwargs):
            observed(*args, **kwargs)
            raise RuntimeError("Fukuda postwrite failure")

        monkeypatch.setattr(engine.fukuda_mistakes, "observe", fail_after_fukuda)
        with pytest.raises(RuntimeError, match="Fukuda postwrite failure"):
            engine._commit_pending()
        assert engine.pending_result is pending
        assert (engine.plan.identity, engine.plan.streak) == (stage, streak)
        assert _durable_counts(engine) == before
        assert engine.fukuda_mistakes.problematic(engine.fingerprint)
        monkeypatch.setattr(engine.fukuda_mistakes, "observe", observed)
        engine._commit_pending()
        assert engine.pending_result is None
        assert not engine.fukuda_mistakes.problematic(engine.fingerprint)
    finally:
        engine.db.close()


def test_failure_after_progress_write_rolls_back_all_evidence_and_plan(
        tmp_path, monkeypatch):
    engine = _engine(tmp_path)
    try:
        _pending(engine, "correct")
        pending = engine.pending_result
        engine.plan.streak = 2  # Force a stage or speed transition.
        before = _durable_counts(engine)
        stage, bpm, streak = (
            engine.plan.identity, engine.plan.bpm, engine.plan.streak)
        old_save = engine.progress.save

        def fail_after_progress(*args, **kwargs):
            old_save(*args, **kwargs)
            raise OSError("disk failed after progress SQL")

        monkeypatch.setattr(engine.progress, "save", fail_after_progress)
        with pytest.raises(OSError, match="disk failed"):
            engine._commit_pending()
        assert engine.pending_result is pending
        assert (engine.plan.identity, engine.plan.bpm, engine.plan.streak) == (
            stage, bpm, streak)
        assert _durable_counts(engine) == before
        monkeypatch.setattr(engine.progress, "save", old_save)
        engine._commit_pending()
        assert engine.pending_result is None
        assert engine.db.execute("SELECT count(*) FROM learning_assessments").fetchone()[0] == 1
        assert engine.db.execute("SELECT count(*) FROM strategy_sessions").fetchone()[0] == 1
    finally:
        engine.db.close()


def test_runtime_settlement_failure_stops_retries_without_losing_pending_take(
        tmp_path, monkeypatch):
    engine = _engine(tmp_path)
    try:
        _pending(engine, "correct")
        pending = engine.pending_result
        engine.auto = True
        engine.visual_transport.next_at = 30.0
        before = _durable_counts(engine)
        real_save = engine.progress.save
        attempts = []

        def fail_after_sql(*args, **kwargs):
            attempts.append(1)
            real_save(*args, **kwargs)
            raise OSError("simulated full disk")

        monkeypatch.setattr(engine.progress, "save", fail_after_sql)
        engine._advance_pending_feedback(31.0)
        assert len(attempts) == 1
        assert engine.pending_result is pending
        assert not engine.auto and engine.visual_transport.next_at == 0
        assert "Could not save" in engine.feedback
        assert _durable_counts(engine) == before
        engine._advance_pending_feedback(31.1)
        assert len(attempts) == 1
        monkeypatch.setattr(engine.progress, "save", real_save)
        engine._commit_pending()
        assert engine.pending_result is None
        assert engine.db.execute(
            "SELECT count(*) FROM learning_assessments").fetchone()[0] == 1
    finally:
        engine.db.close()
