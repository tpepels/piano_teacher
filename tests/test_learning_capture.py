"""Real MIDI/callback lifecycle evidence, distinct from mastery eligibility."""
import json
import sqlite3

import mido
import pytest

from test_mastery_acceptance_contract import practice_factory, _play


def attempts(engine):
    return engine.db.execute(
        "SELECT attempt_id,state,reason,context_json,summary_json FROM learning_attempts "
        "WHERE provenance!='legacy_bounded' ORDER BY rowid").fetchall()


def test_completed_callback_take_retains_actual_match_and_single_settlement(practice_factory):
    engine, clock = practice_factory()
    result = _play(engine, clock, late=(1,))
    rows = attempts(engine)
    assert len(rows) == 1 and rows[0][1] == "completed"
    assert result.passed and not result.clean
    assert engine.db.execute(
        "SELECT passed,clean,mastery_eligible FROM learning_assessments").fetchone() == (1, 0, 1)
    detail = json.loads(engine.db.execute(
        "SELECT detail_json FROM learning_attempt_details").fetchone()[0])
    assert len(detail["observations"]) == 4
    late = detail["observations"][1]
    assert late["actual_pitch"] == 62
    assert late["onset_residual"] == pytest.approx(.25)
    assert late["press_id"] == 1
    engine._commit_pending()
    assert len(attempts(engine)) == 1


@pytest.mark.parametrize("action,kwargs", [
    ("stop", {}), ("restart", {}), ("tempo", {"bpm": 70}),
    ("learn", {}), ("next", {})])
def test_override_keeps_prefix_and_never_invents_future_misses(practice_factory, action, kwargs):
    engine, clock = practice_factory()
    engine.start()
    clock[0] = engine.visual_transport.run_at + .125
    engine._receive(mido.Message("note_on", note=60, velocity=80))
    engine.control(action, **kwargs)
    rows = attempts(engine)
    assert rows[0][1] == "aborted"
    detail = json.loads(engine.db.execute(
        "SELECT detail_json FROM learning_attempt_details WHERE attempt_id=?",
        (rows[0][0],)).fetchone()[0])
    assert len(detail["played"]) == 1
    assert detail["assessment"] is None
    assert detail["observations"] == []
    assert not engine.plan.mastered


def test_failed_assessment_write_retains_same_attempt_and_progress(practice_factory):
    engine, clock = practice_factory()
    engine.db.execute("""CREATE TRIGGER reject_learning_settlement
        BEFORE INSERT ON learning_assessments
        BEGIN SELECT RAISE(ABORT, 'ledger unavailable'); END""")
    with pytest.raises(sqlite3.DatabaseError, match="ledger unavailable"):
        _play(engine, clock)
    attempt = engine.measurement.attempt_id
    assert engine.pending_result is not None
    assert engine.plan.streak == 0
    assert engine.db.execute("SELECT COUNT(*) FROM learning_assessments").fetchone()[0] == 0
    engine.db.execute("DROP TRIGGER reject_learning_settlement")
    engine._commit_pending()
    assert attempts(engine)[0][0] == attempt
    assert engine.plan.streak == 1
    assert engine.db.execute("SELECT COUNT(*) FROM learning_assessments").fetchone()[0] == 1


def test_reset_preserves_evidence_but_delete_piece_erases_credit(practice_factory):
    engine, clock = practice_factory()
    _play(engine, clock)
    count = len(attempts(engine))
    engine.control("reset_path", fingerprint=engine.fingerprint, confirm=True)
    assert len(attempts(engine)) == count
    assert engine.plan.streak == 0
    engine.delete_piece_history(engine.fingerprint, confirm=True)
    assert len(attempts(engine)) == 0
    assert engine.db.execute("SELECT COUNT(*) FROM mastery").fetchone()[0] == 0


def test_new_learner_does_not_inherit_progress(practice_factory):
    engine, clock = practice_factory()
    _play(engine, clock)
    previous = engine.progress.ledger.learner_id
    engine.delete_learner_history(confirm=True)
    assert engine.progress.ledger.learner_id != previous
    assert engine.plan.streak == 0 and not engine.plan.mastered
    assert len(attempts(engine)) == 0


def test_partial_and_preview_are_durable_ineligible_exposures(practice_factory):
    engine, clock = practice_factory()
    _play(engine, clock, from_beat=2.)
    assert engine.db.execute("SELECT mastery_eligible FROM learning_assessments").fetchall() == [(0,)]
    assert json.loads(attempts(engine)[0][3])["scope"] == "partial"
    engine.midi.port = None
    engine.start()
    clock[0] = engine.visual_transport.run_at + 4.21
    engine._update()
    assert json.loads(attempts(engine)[1][3])["scope"] == "preview"
    assert engine.db.execute("SELECT COUNT(*) FROM learning_assessments").fetchone()[0] == 1


def test_rolling_retry_links_first_following_aborted_exposure(practice_factory):
    engine, clock = practice_factory(attacks=tuple((i*.5, (60+i,)) for i in range(8)))
    engine.set_preferences(mistake_response_strategy="adaptive")
    engine.start()
    clock[0] = engine.visual_transport.run_at + 4.21
    engine._update()
    row = attempts(engine)[0]
    assert row[1:3] == ("interrupted", "rolling_recovery")
    assert engine.db.execute("SELECT COUNT(*) FROM learning_decisions").fetchone()[0] == 1
    decision = engine.db.execute("SELECT decision_id FROM learning_decisions").fetchone()[0]
    engine.start()
    engine.control("stop")
    linked = engine.db.execute("SELECT attempt_id,summary_json FROM learning_outcomes WHERE decision_id=? AND json_extract(summary_json,'$.kind')='proximal'",
                               (decision,)).fetchall()
    assert len(linked) == 1
    assert linked[0][0] == attempts(engine)[1][0]
    assert json.loads(linked[0][1])["state"] == "aborted"
    assert json.loads(linked[0][1])["comparability"]["tempo"] is False
    assert engine.db.execute("SELECT COUNT(*) FROM mastery").fetchone()[0] == 0


def test_pause_resume_keeps_attempt_and_records_separate_intervals(practice_factory):
    engine, clock = practice_factory()
    engine.start()
    attempt = engine.measurement.attempt_id
    clock[0] = engine.visual_transport.run_at + .1
    engine._update()
    engine.control("pause")
    clock[0] += 2.
    engine.control("resume")
    assert engine.measurement.attempt_id == attempt
    engine.control("stop")
    events = [json.loads(r[0]) for r in engine.db.execute(
        "SELECT data_json FROM learning_events WHERE kind='phase_intervals'")]
    phases = [item for event in events for item in event["intervals"]]
    assert any(item["phase"] == "pause" and item["end"]-item["start"] == pytest.approx(2.) for item in phases)
    assert any(item["phase"] == "count_in" for item in phases)


def test_device_loss_seals_capture_with_explicit_reason(practice_factory):
    engine, clock = practice_factory()
    engine.start()
    clock[0] = engine.visual_transport.run_at + .1
    engine._receive(mido.Message("note_on", note=60, velocity=80))
    engine._midi_lost("cable_removed")
    assert attempts(engine)[0][1:3] == ("aborted", "cable_removed")


def test_mapped_perform_retains_review_and_never_awards_mastery(practice_factory, monkeypatch):
    from piano_teacher.exercise_contracts import TempoMap, TempoSegment
    engine, clock = practice_factory()
    tempo = TempoMap("replay-two-speed", (TempoSegment(0., 2., 60.), TempoSegment(2., 4., 120.)))
    monkeypatch.setattr(engine, "_active_tempo_map", lambda: tempo)
    engine.start(mode="perform")
    clock[0] = engine.visual_transport.run_at + 3.21
    engine._update()
    assert engine.performance_summary["missed"] == 4
    assert json.loads(attempts(engine)[0][3])["tempo_map_hash"]
    assert engine.db.execute("SELECT mastery_eligible FROM learning_assessments").fetchone() == (0,)
    assert not engine.plan.mastered


def test_guided_preparation_and_capture_roll_back_together(practice_factory, monkeypatch):
    engine, clock = practice_factory()
    engine.control("learn")
    monkeypatch.setattr(engine.teaching, "snapshot", lambda **kwargs:
        {"completed": True, "assisted_count": 1})
    before = engine.db.execute("SELECT * FROM learner_units").fetchall()
    engine.db.execute("""CREATE TRIGGER reject_guided_evidence BEFORE INSERT ON learning_attempt_details
        BEGIN SELECT RAISE(ABORT, 'guided ledger unavailable'); END""")
    with pytest.raises(sqlite3.DatabaseError, match="guided ledger unavailable"):
        engine._save_guided_preparation()
    assert engine.db.execute("SELECT * FROM learner_units").fetchall() == before
    assert not engine.guided_session.prepared
    assert engine.measurement.attempt_id is not None
    engine.db.execute("DROP TRIGGER reject_guided_evidence")
    engine._save_guided_preparation()
    assert engine.guided_session.prepared
    assert engine.measurement.attempt_id is None
    assert engine.db.execute("SELECT COUNT(*) FROM learning_assessments").fetchone()[0] == 0


def test_late_physical_callback_never_writes_sql_and_keeps_timestamp(practice_factory):
    engine, clock = practice_factory()
    engine.start()
    clock[0] = engine.visual_transport.run_at + 8.5
    statements = []
    engine.db.set_trace_callback(statements.append)
    engine._receive(mido.Message("note_on", note=65, velocity=80))
    engine.db.set_trace_callback(None)
    assert not any(sql.lstrip().split()[0].upper() in ("INSERT", "UPDATE", "DELETE", "SAVEPOINT")
                   for sql in statements)
    engine.advance_clock()
    assert engine.midi.input_count == 1


def test_reset_with_real_open_capture_rolls_back_evidence_and_progress(practice_factory):
    engine, clock = practice_factory()
    _play(engine, clock)
    engine.start()
    capture = engine.measurement.attempt_id
    recorder = engine.recorder
    engine.db.execute("""CREATE TRIGGER reject_reset_capture BEFORE UPDATE OF terminal_hash ON learning_attempts
        BEGIN SELECT RAISE(ABORT, 'reset capture unavailable'); END""")
    with pytest.raises(sqlite3.DatabaseError, match="reset capture unavailable"):
        engine.control("reset_path", fingerprint=engine.fingerprint, confirm=True)
    assert engine.plan.streak == 1
    assert engine.db.execute("SELECT streak FROM strategy_sessions").fetchone() == (1,)
    assert engine.measurement.attempt_id == capture and engine.recorder is recorder and engine.running
    assert engine.db.execute("SELECT state FROM learning_attempts WHERE attempt_id=?", (capture,)).fetchone() == ("open",)


def test_checkpoint_write_failure_pauses_and_reports_recording_error(practice_factory):
    engine, clock = practice_factory()
    engine.start()
    engine.db.execute("""CREATE TRIGGER reject_checkpoint BEFORE UPDATE OF checkpoint_json ON learning_attempts
        BEGIN SELECT RAISE(ABORT, 'checkpoint unavailable'); END""")
    clock[0] = engine.visual_transport.run_at + 4.01
    with pytest.raises(sqlite3.DatabaseError, match="checkpoint unavailable"):
        engine._update()
    assert engine.visual_transport.paused
    assert "record" in engine.feedback.lower() or "save" in engine.feedback.lower()
    assert engine.measurement.attempt_id is not None


@pytest.mark.parametrize("whole_learner", [False, True])
def test_delete_failure_preserves_live_capture_and_saved_credit(practice_factory, whole_learner):
    engine, clock = practice_factory()
    _play(engine, clock)
    engine.start()
    capture = engine.measurement.attempt_id
    learner = engine.progress.ledger.learner_id
    engine.db.execute("""CREATE TRIGGER reject_history_delete BEFORE DELETE ON strategy_sessions
        BEGIN SELECT RAISE(ABORT, 'delete unavailable'); END""")
    with pytest.raises(sqlite3.DatabaseError, match="delete unavailable"):
        if whole_learner:
            engine.delete_learner_history(confirm=True)
        else:
            engine.delete_piece_history(engine.fingerprint, confirm=True)
    assert engine.plan.streak == 1 and engine.running
    assert engine.measurement.attempt_id == capture
    assert engine.progress.ledger.learner_id == learner
    assert not engine.measurement.closed
    assert engine.db.execute("SELECT streak FROM strategy_sessions").fetchone() == (1,)


@pytest.mark.parametrize("scope", ["perform", "partial", "section_review", "preview"])
def test_completed_ineligible_exposure_write_failure_pauses(practice_factory, scope):
    engine, clock = practice_factory()
    if scope == "preview":
        engine.midi.port = None
    if scope == "section_review":
        engine.review_end_beat = 2.
    engine.start(mode="perform" if scope == "perform" else "practice",
                 from_beat=2. if scope == "partial" else 0.)
    engine.db.execute("""CREATE TRIGGER reject_ineligible_detail BEFORE INSERT ON learning_attempt_details
        BEGIN SELECT RAISE(ABORT, 'ineligible detail unavailable'); END""")
    clock[0] = engine.visual_transport.run_at + (2. if scope in ("partial", "section_review") else 4.) + .21
    with pytest.raises(sqlite3.DatabaseError, match="ineligible detail unavailable"):
        engine._update()
    assert engine.visual_transport.paused
    assert engine.measurement.attempt_id is not None
    engine.db.execute("DROP TRIGGER reject_ineligible_detail")
    engine.control("resume")
    engine._update()
    assert engine.measurement.attempt_id is None


def test_perform_trouble_and_assessment_settle_atomically(practice_factory):
    engine, clock = practice_factory()
    engine.start(mode="perform")
    engine.db.execute("""CREATE TRIGGER reject_perform_trouble BEFORE INSERT ON learner_units
        BEGIN SELECT RAISE(ABORT, 'perform trouble unavailable'); END""")
    clock[0] = engine.visual_transport.run_at + 4.21
    with pytest.raises(sqlite3.DatabaseError, match="perform trouble unavailable"):
        engine._update()
    assert engine.db.execute("SELECT COUNT(*) FROM learning_assessments").fetchone()[0] == 0
    assert engine.measurement.attempt_id is not None
    engine.db.execute("DROP TRIGGER reject_perform_trouble")
    engine.control("resume")
    engine._update()
    assert engine.db.execute("SELECT COUNT(*) FROM learning_assessments").fetchone()[0] == 1


@pytest.mark.parametrize("direct", [False, True])
def test_calibration_change_seals_the_old_correction_before_new_capture(practice_factory, direct):
    engine, clock = practice_factory()
    engine.set_preferences(midi_offset_ms=100)
    engine.start()
    clock[0] = engine.visual_transport.run_at + .2
    engine._receive(mido.Message("note_on", note=60, velocity=80))
    if direct:
        engine.set_preferences(midi_offset_ms=0)
    else:
        engine.midi_calibration_action("calibration_reset")
    assert not engine.running
    assert attempts(engine)[0][1:3] == ("aborted", "calibration_changed")
    detail = json.loads(engine.db.execute("SELECT detail_json FROM learning_attempt_details").fetchone()[0])
    assert detail["played"][0]["onset"] == pytest.approx(.1)
    assert json.loads(attempts(engine)[0][3])["calibration_ms"] == 100
    assert engine.db.execute("SELECT COUNT(*) FROM learning_events WHERE kind='settings_applied'").fetchone()[0] >= 2


def test_retry_after_failed_full_settlement_saves_same_credit_once(practice_factory):
    engine, clock = practice_factory()
    engine.db.execute("""CREATE TRIGGER reject_retry_assessment BEFORE INSERT ON learning_assessments
        BEGIN SELECT RAISE(ABORT, 'retry unavailable'); END""")
    with pytest.raises(sqlite3.DatabaseError):
        _play(engine, clock)
    attempt_id = engine.measurement.attempt_id
    engine.db.execute("DROP TRIGGER reject_retry_assessment")
    engine.control("restart")
    assert engine.plan.streak == 1
    assert engine.db.execute("SELECT attempt_id,mastery_eligible FROM learning_assessments").fetchall() == [(attempt_id, 1)]


def test_guided_remedial_completion_is_recorded_without_preparation_credit(practice_factory, monkeypatch):
    engine, clock = practice_factory()
    engine.control("learn")
    engine._remediation_active = object()
    monkeypatch.setattr(engine.teaching, "snapshot", lambda **kwargs:
        {"completed": True, "assisted_count": 2})
    before = engine.db.execute("SELECT * FROM learner_units").fetchall()
    engine._save_guided_preparation()
    assert engine.measurement.attempt_id is None
    assert engine.db.execute("SELECT * FROM learner_units").fetchall() == before
    assert not engine.guided_session.prepared
    detail = json.loads(engine.db.execute("SELECT detail_json FROM learning_attempt_details").fetchone()[0])
    assert detail["state"] == "completed" and detail["guidance"]["assisted_count"] == 2
    assert detail["assessment"] is None


def test_completed_perform_does_not_count_idle_review_as_active_practice(practice_factory):
    engine, clock = practice_factory()
    engine.start(mode="perform")
    origin = engine.visual_transport.run_at
    clock[0] = origin+4.21
    engine._update()
    clock[0] += 100.
    engine._update()
    engine.control("stop")
    durations = json.loads(engine.db.execute("SELECT durations_json FROM learning_sessions").fetchone()[0])
    assert durations["active"] <= 4.22
    assert durations.get("feedback", 0) >= 99.


def test_checkpoint_persists_phase_prefix_before_process_loss(practice_factory):
    engine, clock = practice_factory(attacks=tuple((i*.5, (60+i,)) for i in range(8)))
    engine.start()
    clock[0] = engine.visual_transport.run_at + 4.01
    engine._update()
    durations = json.loads(engine.db.execute("SELECT durations_json FROM learning_sessions").fetchone()[0])
    assert durations["active"] >= 4.
    assert durations["count_in"] > 0


def test_repeated_rolling_save_failure_keeps_one_retryable_attempt(practice_factory):
    engine, clock = practice_factory(attacks=tuple((i*.5, (60+i,)) for i in range(8)))
    engine.set_preferences(mistake_response_strategy="adaptive")
    engine.start()
    engine.db.execute("""CREATE TRIGGER reject_rolling_save BEFORE INSERT ON learning_attempt_details
        BEGIN SELECT RAISE(ABORT, 'rolling save unavailable'); END""")
    clock[0] = engine.visual_transport.run_at+4.21
    with pytest.raises(sqlite3.DatabaseError, match="rolling save unavailable"):
        engine._update()
    attempt = engine.measurement.attempt_id
    with pytest.raises(sqlite3.DatabaseError, match="rolling save unavailable"):
        engine.control("restart")
    assert engine.measurement.attempt_id == attempt and engine.visual_transport.paused
    assert engine.plan.bpm == 60
    engine.db.execute("DROP TRIGGER reject_rolling_save")
    engine.control("restart")
    assert engine.measurement.attempt_id is None and not engine.visual_transport.paused
    assert engine.db.execute("SELECT attempt_id FROM learning_assessments").fetchall() == [(attempt,)]
    assert engine.db.execute("SELECT COUNT(*) FROM learning_decisions").fetchone() == (1,)


def test_graceful_engine_close_ends_session_and_live_exposure_once(practice_factory):
    from piano_teacher.progress_repository import ProgressRepository
    engine, clock = practice_factory()
    engine.start()
    session = engine.measurement.session_id
    engine.close()
    engine.close()
    reopened = ProgressRepository(engine._data_dir / "progress.db")
    try:
        reason, ended = reopened.db.execute("SELECT closure_reason,ended_utc FROM learning_sessions WHERE session_id=?", (session,)).fetchone()
        assert reason == "shutdown" and ended
        assert reopened.db.execute("SELECT state,reason FROM learning_attempts").fetchall() == [("aborted", "shutdown")]
        assert reopened.db.execute("SELECT COUNT(*) FROM learning_assessments").fetchone() == (0,)
    finally:
        reopened.close()


def test_suggested_export_path_is_usable_without_precreating_folder(practice_factory):
    from pathlib import Path
    engine, clock = practice_factory()
    _play(engine, clock)
    path = engine.learning_history_status()["default_path"]
    result = engine.export_learning_history(path, include_detail=True)
    assert Path(result["path"]).is_file()
    assert json.loads(Path(path).read_text())["attempts"]


def test_reset_records_its_action_in_its_own_atomic_event(practice_factory):
    from piano_teacher.inprocess import EngineCommands, OK
    engine, clock = practice_factory()
    _play(engine, clock)
    engine.start()
    engine.db.execute("""CREATE TRIGGER reject_duplicate_reset_log BEFORE INSERT ON learning_events
        WHEN NEW.kind='manual_action'
        BEGIN SELECT RAISE(ABORT, 'duplicate action unavailable'); END""")
    status, reply = EngineCommands(engine=engine).request("practice.command", json.dumps({
        "action": "reset_path", "fingerprint": engine.fingerprint, "confirm": True}))
    assert status == OK, reply
    assert engine.plan.streak == 0 and not engine.running
    assert engine.db.execute("SELECT COUNT(*) FROM learning_events WHERE kind='lesson_reset'").fetchone() == (1,)


@pytest.mark.parametrize("all_learner", [False, True])
def test_history_deletion_clears_guided_route_and_assistance(practice_factory, all_learner):
    engine, clock = practice_factory()
    engine.control("learn")
    engine.control("hints", enabled=True)
    assert engine.course_guided and engine.persistent_hints
    if all_learner:
        engine.delete_learner_history(confirm=True)
    else:
        engine.delete_piece_history(engine.fingerprint, confirm=True)
    assert not engine.course_guided and not engine.persistent_hints
    assert engine.teaching is None and engine.mode == "practice"
    engine.start()
    assert engine.measurement.context["assistance"] is False


@pytest.mark.parametrize("action,values", [("stop", {}), ("tempo", {"bpm": 70})])
def test_piece_deletion_removes_manual_action_source_and_tempo_facts(practice_factory, tmp_path, action, values):
    engine, clock = practice_factory()
    engine.start()
    fingerprint = engine.fingerprint
    engine.control(action, **values)
    assert engine.db.execute("SELECT fingerprint FROM learning_events WHERE kind='manual_action'").fetchone() == (fingerprint,)
    engine.delete_piece_history(fingerprint, confirm=True)
    path = tmp_path / "deleted-piece.json"
    engine.export_learning_history(str(path), include_detail=True)
    assert fingerprint not in path.read_text()


@pytest.mark.parametrize("policy", ["adaptive", "steady-repeat", "slow-practice", "micro-loop", "guided-repair", "finish-then-review"])
def test_fixed_policy_replay_retains_selected_decision_and_canceled_episode(practice_factory, policy):
    engine, clock = practice_factory(attacks=tuple((i*.5, (60+i,)) for i in range(8)))
    engine.set_preferences(mistake_response_strategy=policy)
    engine.start()
    clock[0] = engine.visual_transport.run_at+4.21
    engine._update()
    if engine.pending_result is not None:
        engine._commit_pending()
    engine.control("stop")
    decision = json.loads(engine.db.execute("SELECT data_json FROM learning_decisions").fetchone()[0])
    assert decision["policy"] == policy
    assert decision["parameters"]["policy_id"] == policy
    assert decision["wrong_missed_source_ids"]
    assert engine.db.execute("SELECT COUNT(*) FROM learning_outcomes WHERE json_extract(summary_json,'$.state')='censored'").fetchone()[0] >= 1
    assert not engine.plan.mastered
