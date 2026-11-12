"""A rejected typed reset cannot delete only part of a learner's records."""
from __future__ import annotations

import json
import sqlite3

import pytest

from piano_teacher import server
from piano_teacher.inprocess import EngineCommands, FAILED, INVALID, OK
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.practice import Assessment, NoteAssessment, Recorder
from piano_teacher.server import PracticeEngine


HISTORY_TABLES = ("learning_attempts", "learning_assessments", "learning_attempt_details")
TABLES = (*HISTORY_TABLES,
    "strategy_sessions", "learner_units", "learner_stages",
    "repeat_tempo_credit", "stage_tempos", "mastery", "sessions",
    "fukuda_mistakes",
)


def _piece():
    notes = tuple(Note(float(i), float(i) + .5, 60 + i, 0, 0,
                       "right", f"source-{i}") for i in range(8))
    phrase = Phrase(1, 1, 2, 0., 8., notes)
    return Piece("Atomic reset", 110, notes, (phrase,),
                 bar_boundaries=(0., 4., 8.))


def _seed_piece(engine, fingerprint, plan):
    plan.set_bpm(66)
    plan.streak = 2
    plan.mastered[plan.identity] = 110
    plan.transferable_tempos.add(plan.identity)
    engine.progress.save(plan, fingerprint)
    unit = {"start_beat": 0., "end_beat": 4., "first_bar": 1,
            "last_bar": 1, "source_indices": [0], "required_notes": 1}
    engine.learner_store.complete_unit(fingerprint, plan.identity, unit)
    engine.learner_store.record_trouble(
        fingerprint, plan.identity, unit, errors=1, pitches=[60])
    engine.learner_store.save_resume(fingerprint, plan.identity, unit)
    engine.learner_store.mark_skipped(
        fingerprint, plan.identity, reason="Deliberate placement")
    ledger = engine.progress.ledger
    attempt = f"seed-{fingerprint}"
    ledger.start_attempt(attempt, engine.measurement.session_id, {
        "fingerprint": fingerprint, "stage_key": plan.identity,
        "performed_bpm": 66, "target_bpm": 110, "scope": "full"})
    ledger.settle_attempt(attempt, {
        "state": "completed", "reason": "full_passage",
        "ended_utc": "2026-11-04T10:00:05Z", "monotonic_end": 5.,
        "assessment": {"bpm": 66, "statuses": ["missed"], "extra_notes": 0,
                       "clean": False, "passed": False, "mastery_eligible": False},
        "observations": [], "played": []})
    engine.fukuda_mistakes.observe(
        fingerprint, Assessment((NoteAssessment(plan.piece.notes[0], "missed"),), 0))


def _records(db, fingerprint):
    records = {}
    for table in TABLES:
        if table in ("learning_assessments", "learning_attempt_details"):
            query = (f"SELECT evidence.* FROM {table} evidence "
                     "JOIN learning_attempts attempt USING(attempt_id) "
                     "WHERE attempt.fingerprint=? ORDER BY evidence.rowid")
        else:
            query = f"SELECT * FROM {table} WHERE fingerprint=? ORDER BY rowid"
        records[table] = db.execute(query, (fingerprint,)).fetchall()
    return records


@pytest.mark.parametrize("failure", ["delete", "generator", "save"])
def test_typed_reset_rolls_back_all_records_and_preserves_active_take_on_failure(
        tmp_path, monkeypatch, failure):
    # Removing the encompassing reset transaction must fail this test: the
    # progress delete would commit before the later Fukuda delete is rejected.
    engine = PracticeEngine(tmp_path, enable_midi=False)
    try:
        engine.plan = LearningPlan(_piece())
        engine.fingerprint = "selected"
        _seed_piece(engine, "selected", engine.plan)
        _seed_piece(engine, "other", LearningPlan(_piece()))
        engine.recorder = Recorder()
        engine.recorder.add(60, True, .125)
        engine.running = True
        engine.transport_id = 17
        engine.visual_transport.run_at = 1234.5
        engine.score_revision = 9
        plan = engine.plan
        recorder = engine.recorder
        before_plan = (plan.identity, plan.bpm, plan.streak,
                       dict(plan.mastered), dict(plan.stage_tempos))
        before_records = _records(engine.db, "selected")
        other_records = _records(engine.db, "other")
        assert all(before_records.values())
        original_plan_type = server.LearningPlan
        if failure == "delete":
            with engine.db:
                engine.db.execute("""CREATE TRIGGER reject_selected_reset
                    BEFORE DELETE ON fukuda_mistakes
                    WHEN OLD.fingerprint='selected'
                    BEGIN SELECT RAISE(ABORT, 'injected reset failure'); END""")
        elif failure == "save":
            with engine.db:
                engine.db.execute("""CREATE TRIGGER reject_selected_reset
                    BEFORE INSERT ON strategy_sessions
                    WHEN NEW.fingerprint='selected'
                    BEGIN SELECT RAISE(ABORT, 'injected reset failure'); END""")
        else:
            def reject_replacement(*args, **kwargs):
                raise RuntimeError("injected reset failure")
            monkeypatch.setattr(server, "LearningPlan", reject_replacement)
        commands = EngineCommands(engine=engine)
        payload = json.dumps({"action": "reset_path", "fingerprint": "selected",
                              "confirm": True})

        status, response = commands.request("practice.command", payload)

        assert status == (INVALID if failure == "generator" else FAILED)
        assert "injected reset failure" in json.loads(response)["error"]
        assert _records(engine.db, "selected") == before_records
        assert _records(engine.db, "other") == other_records
        with sqlite3.connect(tmp_path / "progress.db") as reopened:
            assert _records(reopened, "selected") == before_records
            assert _records(reopened, "other") == other_records
        assert engine.plan is plan
        assert (plan.identity, plan.bpm, plan.streak,
                plan.mastered, plan.stage_tempos) == before_plan
        assert engine.recorder is recorder
        assert [(note.pitch, note.onset, note.release)
                for note in recorder.presses] == [(60, .125, None)]
        assert engine.running
        assert engine.transport_id == 17
        assert engine.visual_transport.run_at == 1234.5
        assert engine.score_revision == 9

        if failure != "generator":
            with engine.db:
                engine.db.execute("DROP TRIGGER reject_selected_reset")
        else:
            monkeypatch.setattr(server, "LearningPlan", original_plan_type)

        status, response = commands.request("practice.command", payload)

        assert status == OK, response
        assert engine.plan is not plan
        assert engine.plan.lesson_step_number == 1
        assert engine.plan.streak == 0
        assert not engine.plan.mastered
        assert not engine.running
        assert engine.recorder is None
        assert engine.score_revision == 10
        assert _records(engine.db, "other") == other_records
        reset_records = _records(engine.db, "selected")
        for table in TABLES:
            if table in HISTORY_TABLES:
                assert reset_records[table] == before_records[table], table
                continue
            assert len(reset_records[table]) == (
                1 if table in ("sessions", "strategy_sessions", "stage_tempos") else 0), table
        with sqlite3.connect(tmp_path / "progress.db") as reopened:
            assert _records(reopened, "selected") == reset_records
            assert _records(reopened, "other") == other_records
    finally:
        engine.db.close()
