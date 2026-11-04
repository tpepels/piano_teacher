"""Real-file contracts for the one authoritative local evidence ledger."""
import json
import sqlite3

import pytest

from piano_teacher.progress_repository import ProgressRepository
from piano_teacher.sqlite_transaction import sqlite_atomic


@pytest.fixture
def repository(tmp_path):
    repository = ProgressRepository(tmp_path / "progress.db")
    assert hasattr(repository, "ledger"), "ProgressRepository must own the learning ledger"
    yield repository
    repository.close()


def start(ledger, *, session="session-1", attempt="attempt-1", piece="source-1", extra=None):
    ledger.start_session(session, "run-1", "2026-01-01T10:00:00Z", "Europe/Lisbon")
    rule = ledger.store_rules({"mastery": "accepted-full-target-v1", "threshold": 0.5})
    context = {"fingerprint": piece, "stage_key": "stage-1", "rule_id": rule,
               "hand": "both", "scope": "full", "classification": "full", "started_utc": "2026-01-01T10:00:01Z",
               "monotonic_start": 1.0, "target_bpm": 90, "performed_bpm": 90}
    context.update(extra or {})
    ledger.start_attempt(attempt, session, context)
    return context


def terminal(**changes):
    result = {"state": "completed", "reason": "deadline", "ended_utc": "2026-01-01T10:00:05Z",
              "monotonic_end": 5.0,
              "assessment": {"statuses": ["correct", "late"], "extra_notes": 0, "bpm": 90,
                             "clean": False, "passed": True, "mastery_eligible": True},
              "observations": [{"source_id": "note-1", "onset_residual_seconds": -0.0123456}],
              "played": [{"pitch": 60, "onset": 1.0, "release": 2.0}]}
    result.update(changes)
    return result


def test_settlement_replays_once_and_survives_real_reopen(repository, tmp_path):
    ledger = repository.ledger
    learner = ledger.learner_id
    start(ledger)
    assert ledger.settle_attempt("attempt-1", terminal()) is True
    assert ledger.settle_attempt("attempt-1", terminal()) is False
    with pytest.raises(ValueError, match="(?i)conflict|different"):
        ledger.settle_attempt("attempt-1", terminal(reason="changed"))
    reopened = ProgressRepository(tmp_path / "progress.db")
    try:
        assert reopened.ledger.learner_id == learner
        assert reopened.ledger.settle_attempt("attempt-1", terminal()) is False
        history = reopened.ledger.recent("source-1", "stage-1")
        assert len(history.recent) == 1
        assert history.recent[0].statuses == ("correct", "late")
        assert reopened.db.execute("SELECT passed,clean FROM learning_assessments").fetchall() == [(1, 0)]
    finally:
        reopened.close()


def test_all_writers_share_outer_rollback_and_then_retry(repository):
    ledger = repository.ledger
    start(ledger)
    with pytest.raises(RuntimeError, match="progress failure"):
        with sqlite_atomic(repository.db):
            ledger.settle_attempt("attempt-1", terminal())
            ledger.record_event("session-1", "feedback", {"reason": "scored"}, event_id="event-1")
            ledger.add_decision("decision-1", "session-1", "attempt-1", {"policy": "repeat"})
            ledger.record_outcome("outcome-1", "decision-1", "attempt-1", {"state": "observed"})
            raise RuntimeError("progress failure")
    assert repository.db.execute("SELECT state FROM learning_attempts").fetchall() == [("open",)]
    for table in ("learning_assessments", "learning_events", "learning_decisions", "learning_outcomes"):
        assert repository.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
    assert ledger.settle_attempt("attempt-1", terminal()) is True


def test_rule_hashes_and_all_payloads_reject_nonfinite_json(repository):
    ledger = repository.ledger
    assert ledger.store_rules({"a": 1, "b": 2}) == ledger.store_rules({"b": 2, "a": 1})
    with pytest.raises(ValueError):
        ledger.store_rules({"nested": [float("nan")]})
    start(ledger)
    with pytest.raises(ValueError):
        ledger.checkpoint("attempt-1", {"played": [float("inf")]})
    with pytest.raises(ValueError):
        ledger.settle_attempt("attempt-1", terminal(monotonic_end=float("inf")))
    assert repository.db.execute("SELECT state FROM learning_attempts").fetchone()[0] == "open"


def test_recovery_keeps_only_captured_prefix_and_unknown_crash_suffix(repository, tmp_path):
    start(repository.ledger)
    repository.ledger.checkpoint("attempt-1", {"played": [{"pitch": 60, "onset": 1.2}],
                                               "monotonic_checkpoint": 2.0})
    reopened = ProgressRepository(tmp_path / "progress.db")
    try:
        assert reopened.db.execute("SELECT state FROM learning_attempts").fetchone()[0] == "open"
        assert reopened.ledger.recover_open_sessions() == 1
        assert reopened.ledger.recover_open_sessions() == 0
        path = tmp_path / "recovered.json"
        reopened.ledger.export(path, include_detail=True)
        exported = json.loads(path.read_text())
        attempt = exported["attempts"][0]
        assert attempt["state"] == "process_interrupted"
        assert attempt["ended_utc"] is None
        assert attempt["detail"]["capture_suffix"] == "unknown"
        assert attempt["detail"]["played"] == [{"onset": 1.2, "pitch": 60}]
        assert not exported["assessments"]
        assert exported["sessions"][0]["ended_utc"] is None
        assert exported["sessions"][0]["closure_reason"] == "process_interrupted"
        assert exported["sessions"][0]["recovered_utc"]
    finally:
        reopened.close()


@pytest.mark.parametrize("fill_budget", [False, True])
def test_recovery_near_budget_does_not_duplicate_prefix_or_block_startup(repository, fill_budget):
    ledger = repository.ledger
    ledger.prune(days=365, budget_mib=16)
    start(ledger)
    size = 9_000_000
    if fill_budget:
        base = ledger.status()["logical_detail_bytes"]
        envelope = len(json.dumps({"played": [{"payload": ""}]}, sort_keys=True, separators=(",", ":")))
        size = 16*1024*1024-base-envelope
    ledger.checkpoint("attempt-1", {"played": [{"payload": "x"*size}]})
    assert ledger.recover_open_sessions() == 1
    assert repository.db.execute("SELECT state FROM learning_attempts").fetchone() == ("process_interrupted",)
    assert repository.db.execute("SELECT COUNT(*) FROM learning_assessments").fetchone() == (0,)
    detail = repository.db.execute("SELECT detail_json FROM learning_attempt_details").fetchone()
    if detail:
        payload = json.loads(detail[0])
        assert payload["played"][0]["payload"] == "x"*size
        assert "played" not in (payload.get("checkpoint") or {})
    else:
        assert ledger.status()["coverage"]["pruned_detail_attempts"] == 1
    assert ledger.status()["logical_detail_bytes"] <= 16*1024*1024


def test_export_redacts_preferences_and_keeps_derived_microsecond_residuals(repository, tmp_path):
    ledger = repository.ledger
    start(ledger)
    ledger.record_event("session-1", "settings_intent", {"after": {
        "music_dir": "/private/piano", "midi_device": "Tom's keyboard", "last_piece": "private.mid"}})
    ledger.settle_attempt("attempt-1", {"state": "aborted", "reason": "stop", "assessment": None,
        "observations": [{"onset_residual": -.1234567}], "played": []})
    path = tmp_path / "private-export.json"
    ledger.export(path, include_detail=True)
    text = path.read_text()
    assert "/private/piano" not in text and "Tom's keyboard" not in text and "private.mid" not in text
    data = json.loads(text)
    assert data["attempts"][0]["detail"]["observations"][0]["onset_residual_microseconds"] == -123457


def test_crash_censors_episode_even_when_proximal_exposure_was_observed(repository):
    ledger = repository.ledger
    context = start(ledger)
    ledger.settle_attempt("attempt-1", terminal())
    ledger.add_decision("decision-1", "session-1", "attempt-1", {"policy": "repeat", "episode_id": "episode-1"})
    ledger.start_attempt("attempt-2", "session-1", context)
    ledger.settle_attempt("attempt-2", terminal())
    ledger.record_outcome("decision-1:proximal", "decision-1", "attempt-2", {"kind": "proximal", "state": "observed"})
    assert ledger.recover_open_sessions() == 1
    row = repository.db.execute("SELECT summary_json FROM learning_outcomes WHERE outcome_id='episode-1:verification'").fetchone()
    assert row is not None
    assert json.loads(row[0]) == {"kind": "episode_verification", "episode_id": "episode-1",
                                "state": "censored", "reason": "process_interrupted"}
    assert ledger.recover_open_sessions() == 0


def test_capture_censors_prior_episode_before_different_stage_exposure(repository):
    from piano_teacher.application.learning_capture import LearningCapture
    capture = LearningCapture(repository.ledger)
    context = {"fingerprint": "source", "stage_key": "stage-a", "hand": "both",
               "target_bpm": 90, "performed_bpm": 90, "scope": "full"}
    capture.begin(context)
    capture.seal([], state="interrupted", reason="rolling_recovery")
    decision = capture.decision({"policy": "repeat"})
    with capture.atomic():
        capture.persist()
    capture.finish()
    capture.begin({**context, "stage_key": "stage-b"})
    assert capture.context["parent_decision_id"] is None
    outcomes = [json.loads(row[0]) for row in repository.db.execute(
        "SELECT summary_json FROM learning_outcomes WHERE decision_id=?", (decision,))]
    assert len(outcomes) == 2 and all(row["state"] == "censored" for row in outcomes)


def test_piece_deletion_removes_previously_unlinked_manual_source_references(repository):
    ledger = repository.ledger
    start(ledger)
    ledger.record_event("session-1", "manual_action", {"action": "stop",
        "before": {"fingerprint": "source-1", "bpm": 90},
        "after": {"fingerprint": "source-1", "bpm": 90}}, event_id="unlinked-source")
    ledger.record_event("session-1", "manual_action", {"action": "stop",
        "before": {"fingerprint": "other-source", "bpm": 70}}, event_id="unrelated-source")
    ledger.delete_piece("source-1")
    assert repository.db.execute("SELECT event_id FROM learning_events").fetchall() == [("unrelated-source",)]


@pytest.mark.parametrize("state", ["aborted", "interrupted", "completed"])
def test_only_completed_original_target_exposure_settles_episode_verification(repository, state):
    from piano_teacher.application.learning_capture import LearningCapture
    from piano_teacher.music import Note
    from piano_teacher.practice import Assessment, NoteAssessment
    capture = LearningCapture(repository.ledger)
    context = {"fingerprint": "source", "stage_key": "stage-a", "hand": "both",
               "target_bpm": 90, "performed_bpm": 90, "scope": "full",
               "bar_boundaries": [0., 4.], "phrase_start": 0., "end_beat": 4.}
    capture.begin(context)
    capture.seal([], state="interrupted", reason="rolling_recovery")
    capture.decision({"policy": "repeat"})
    episode = capture.episode["id"]
    with capture.atomic():
        capture.persist()
    capture.finish()
    capture.begin(context)
    if state == "aborted":
        capture.interrupt("stop")
    else:
        result = Assessment((NoteAssessment(Note(0., .25, 60, 0, 0), "correct"),), 0)
        capture.seal([], state=state, reason="deadline" if state == "completed" else "rolling_recovery", result=result)
        if state == "interrupted":
            capture.decision({"policy": "repeat"})
            assert capture.episode["id"] == episode
        with capture.atomic():
            capture.persist()
        capture.finish()
        if state == "interrupted":
            assert repository.db.execute("SELECT 1 FROM learning_outcomes WHERE outcome_id=?", (episode+":verification",)).fetchone() is None
            assert capture.episode["id"] == episode
            capture.censor("stage_changed")
    encoded = repository.db.execute("SELECT summary_json FROM learning_outcomes WHERE outcome_id=?", (episode+":verification",)).fetchone()
    assert encoded is not None
    outcome = json.loads(encoded[0])
    assert outcome["state"] == ("completed" if state == "completed" else "censored")
    assert outcome["reason"] == {"aborted": "stop", "interrupted": "stage_changed", "completed": "original_target_test"}[state]
    assert capture.episode is None


def test_events_decisions_outcomes_have_stable_conflict_checked_identity(repository):
    ledger = repository.ledger
    start(ledger)
    assert ledger.record_event("session-1", "pause", {"at": 2}, attempt_id="attempt-1", event_id="event-1") == "event-1"
    ledger.record_event("session-1", "pause", {"at": 2}, attempt_id="attempt-1", event_id="event-1")
    with pytest.raises(ValueError):
        ledger.record_event("session-1", "resume", {"at": 2}, event_id="event-1")
    ledger.add_decision("decision-1", "session-1", "attempt-1", {"policy": "repeat"})
    ledger.add_decision("decision-1", "session-1", "attempt-1", {"policy": "repeat"})
    with pytest.raises(ValueError):
        ledger.add_decision("decision-1", "session-1", "attempt-1", {"policy": "stop"})
    ledger.record_outcome("outcome-1", "decision-1", "attempt-1", {"state": "observed"})
    ledger.record_outcome("outcome-1", "decision-1", "attempt-1", {"state": "observed"})
    with pytest.raises(ValueError):
        ledger.record_outcome("outcome-1", "decision-1", "attempt-1", {"state": "censored"})
    assert repository.db.execute("SELECT count(*) FROM learning_outcomes").fetchone()[0] == 1


@pytest.mark.parametrize("failed_kind", ["proximal", "episode_verification"])
def test_direct_interruption_rolls_back_attempt_and_capture_until_all_outcomes_save(repository, failed_kind):
    from piano_teacher.application.learning_capture import LearningCapture
    capture = LearningCapture(repository.ledger)
    context = {"fingerprint": "source", "stage_key": "stage-a", "hand": "both",
               "target_bpm": 90, "performed_bpm": 90, "scope": "full",
               "bar_boundaries": [0., 4.], "phrase_start": 0., "end_beat": 4.}
    capture.begin(context)
    capture.seal([], state="interrupted", reason="rolling_recovery")
    decision = capture.decision({"policy": "repeat"})
    with capture.atomic():
        capture.persist()
    capture.finish()
    capture.begin(context)
    attempt = capture.attempt_id
    episode = capture.episode.copy()
    repository.db.execute(f"""CREATE TRIGGER reject_interruption_outcome
        BEFORE INSERT ON learning_outcomes
        WHEN json_extract(NEW.summary_json, '$.kind')='{failed_kind}'
        BEGIN SELECT RAISE(ABORT, 'outcome unavailable'); END""")
    with pytest.raises(sqlite3.DatabaseError, match="outcome unavailable"):
        capture.interrupt("restart")
    assert repository.db.execute("SELECT state FROM learning_attempts WHERE attempt_id=?", (attempt,)).fetchone() == ("open",)
    assert capture.attempt_id == attempt and capture.sealed is None
    assert capture.parent_decision == decision and capture.episode == episode
    assert repository.db.execute("SELECT count(*) FROM learning_outcomes").fetchone() == (0,)
    repository.db.execute("DROP TRIGGER reject_interruption_outcome")
    capture.interrupt("restart")
    assert repository.db.execute("SELECT state,reason FROM learning_attempts WHERE attempt_id=?", (attempt,)).fetchone() == ("aborted", "restart")
    assert capture.attempt_id is None and capture.episode is None
    assert repository.db.execute("SELECT count(*) FROM learning_outcomes").fetchone() == (2,)


def test_history_reads_settlement_order_and_only_real_assessments(repository):
    ledger = repository.ledger
    start(ledger)
    for index in range(2, 12):
        ledger.start_attempt(f"attempt-{index}", "session-1", {"fingerprint": "source-1", "stage_key": "stage-1", "scope": "full"})
    for index in reversed(range(1, 12)):
        value = terminal()
        value["assessment"]["bpm"] = 60 + index
        ledger.settle_attempt(f"attempt-{index}", value)
    ledger.start_attempt("preview", "session-1", {"fingerprint": "source-1", "stage_key": "stage-1"})
    ledger.settle_attempt("preview", terminal(assessment=None))
    assert [e.bpm for e in ledger.recent("source-1", "stage-1").recent] == [68., 67., 66., 65., 64., 63., 62., 61.]
    assert not ledger.recent("source-1", "other").recent
    with pytest.raises(ValueError):
        ledger.recent("source-1", "stage-1", 65)


def test_prune_keeps_summaries_coverage_and_open_detail(repository, tmp_path):
    ledger = repository.ledger
    start(ledger)
    ledger.settle_attempt("attempt-1", terminal())
    ledger.close_session("session-1", "shutdown")
    start(ledger, session="session-2", attempt="pending")
    ledger.checkpoint("pending", {"played": [{"pitch": 65}]})
    result = ledger.prune(days=7, budget_mib=16, now_utc="2027-01-01T00:00:00Z")
    assert result["pruned_attempts"] == 1
    assert ledger.status()["coverage"]["pruned_detail_attempts"] == 1
    assert not ledger.recent("source-1", "stage-1").recent
    ledger.export(tmp_path / "pruned.json", include_detail=True)
    exported = json.loads((tmp_path / "pruned.json").read_text())
    by_id = {a["attempt_id"]: a for a in exported["attempts"]}
    assert by_id["attempt-1"]["detail"] is None
    assert by_id["attempt-1"]["detail_pruned"] is True
    assert by_id["attempt-1"]["summary"]["terminal"]["monotonic_end"] == 5.0
    assert by_id["pending"]["checkpoint"]["played"] == [{"pitch": 65}]
    assert exported["coverage"]["pruned_detail_attempts"] == 1
    assert exported["coverage"]["pruned_detail_sessions"] == 1
    assessment = exported["assessments"][0]
    assert assessment["statuses"] == []
    assert assessment["summary"]["status_counts"] == {"correct": 1, "late": 1}
    assert assessment["summary"]["note_count"] == 2
    assert "statuses" not in assessment["summary"]
    assert assessment["passed"] is True and assessment["clean"] is False


def test_advisory_history_excludes_perform_partial_guided_and_interrupted(repository):
    ledger = repository.ledger
    context = start(ledger)
    for index, scope in enumerate(("perform", "partial", "guided", "section_review", "preview")):
        ledger.start_attempt(f"excluded-{index}", "session-1", {**context, "scope": scope})
        ledger.settle_attempt(f"excluded-{index}", terminal())
    ledger.start_attempt("interrupted", "session-1", context)
    ledger.settle_attempt("interrupted", terminal(state="aborted"))
    value = terminal()
    value["assessment"].update(bpm=70, mastery_eligible=False)
    ledger.settle_attempt("attempt-1", value)
    assert [item.bpm for item in ledger.recent("source-1", "stage-1").recent] == [70.]


def test_session_phase_durations_accumulate_once_and_rollback(repository):
    ledger = repository.ledger
    start(ledger)
    data = {"intervals": [{"phase": "active", "start": 1.0, "end": 3.5},
                          {"phase": "pause", "start": 3.5, "end": 5.0}],
            "units": "monotonic_seconds"}
    ledger.record_event("session-1", "phase_intervals", data, event_id="intervals-1")
    ledger.record_event("session-1", "phase_intervals", data, event_id="intervals-1")
    assert json.loads(repository.db.execute("SELECT durations_json FROM learning_sessions").fetchone()[0]) == {"active": 2.5, "pause": 1.5}
    with pytest.raises(RuntimeError):
        with sqlite_atomic(repository.db):
            ledger.record_event("session-1", "phase_intervals", data, event_id="intervals-2")
            raise RuntimeError("rollback")
    assert json.loads(repository.db.execute("SELECT durations_json FROM learning_sessions").fetchone()[0]) == {"active": 2.5, "pause": 1.5}
    with pytest.raises(ValueError):
        ledger.record_event("session-1", "phase_intervals", {"intervals": [{"phase": "active", "start": 9, "end": 3}]})


def test_recovery_marks_unconfirmed_settings_intent_unknown(repository, tmp_path):
    ledger = repository.ledger
    start(ledger)
    ledger.record_event("session-1", "settings_intent", {"intent_id": "intent-1", "after": {"detail_days": 7}})
    ledger.record_event("session-1", "settings_intent", {"intent_id": "intent-2", "after": {"detail_days": 8}})
    ledger.record_event("session-1", "settings_applied", {"intent_id": "intent-2"})
    ledger.recover_open_sessions()
    ledger.export(tmp_path / "settings.json")
    events = json.loads((tmp_path / "settings.json").read_text())["events"]
    uncertain = [event["data"] for event in events if event["kind"] == "settings_uncertain"]
    assert len(uncertain) == 1 and uncertain[0]["intent_id"] == "intent-1"
    assert uncertain[0]["applied"] is None


def test_budget_prunes_old_closed_session_but_rolls_back_oversize_pending(repository):
    ledger = repository.ledger
    start(ledger)
    ledger.settle_attempt("attempt-1", terminal(played=[{"padding": "x" * 9_000_000}]))
    ledger.close_session("session-1", "shutdown")
    start(ledger, session="session-2", attempt="pending")
    ledger.prune(days=3650, budget_mib=16, now_utc="2026-01-02T00:00:00Z")
    ledger.checkpoint("pending", {"padding": "y" * 9_000_000})
    assert ledger.status()["coverage"]["pruned_detail_attempts"] == 1
    before = ledger.status()["logical_detail_bytes"]
    with pytest.raises(ValueError, match="budget|limit"):
        ledger.checkpoint("pending", {"padding": "z" * 17_000_000})
    assert ledger.status()["logical_detail_bytes"] == before
    assert repository.db.execute("SELECT state FROM learning_attempts WHERE attempt_id='pending'").fetchone()[0] == "open"


def test_checkpoint_does_not_scan_unrelated_retained_note_payloads(repository):
    ledger = repository.ledger
    start(ledger)
    ledger.settle_attempt("attempt-1", terminal())
    ledger.close_session("session-1", "shutdown")
    start(ledger, session="session-2", attempt="pending")
    repository.db.set_authorizer(lambda action, table, *_: sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_READ and table == "learning_attempt_details" else sqlite3.SQLITE_OK)
    try:
        ledger.checkpoint("pending", {"played": [{"pitch": 60}], "label": "é"})
    finally:
        repository.db.set_authorizer(None)
    before = ledger.status()["logical_detail_bytes"]
    ledger.checkpoint("pending", {"played": [{"pitch": 60}], "label": "éé"})
    assert ledger.status()["logical_detail_bytes"] == before + 2


def test_export_is_local_versioned_redacted_and_detail_is_explicit(repository, tmp_path):
    ledger = repository.ledger
    start(ledger, extra={"source_path": "/home/private/secret.mid", "piece_name": "Secret Sonata",
                         "device": {"name": "Personal keyboard", "calibration_ms": 12},
                         "tempo_map": [{"beat": 0, "seconds_per_beat": 0.6666666667}]})
    ledger.settle_attempt("attempt-1", terminal())
    ledger.record_event("session-1", "device", {"device_name": "Personal keyboard", "reason": "reconnect"})
    path = tmp_path / "export.json"
    ledger.export(path)
    raw = path.read_text()
    result = json.loads(raw)
    assert result["schema_version"] == 1
    assert result["units"]["residuals"] == "seconds"
    assert result["missingness"]["unknown"]
    assert result["attempts"][0]["detail"] is None
    assert "secret.mid" not in raw and "Secret Sonata" not in raw and "Personal keyboard" not in raw
    ledger.export(path, include_detail=True)
    details = json.loads(path.read_text())["attempts"][0]["detail"]
    assert details["observations"][0]["onset_residual_seconds"] == -0.0123456
    assert details["observations"][0]["onset_residual_microseconds"] == -12346


def test_reset_preserves_history_and_delete_piece_removes_all_linked_learning(repository):
    ledger = repository.ledger
    start(ledger)
    ledger.settle_attempt("attempt-1", terminal())
    ledger.add_decision("decision-1", "session-1", "attempt-1", {"rule_id": "unused"})
    ledger.record_outcome("outcome-1", "decision-1", "attempt-1", {"state": "observed"})
    ledger.record_event("session-1", "tempo", {"fingerprint": "source-1"}, attempt_id="attempt-1")
    repository.db.execute("INSERT INTO mastery VALUES ('source-1','stage-1',90)")
    repository.db.execute("CREATE TABLE IF NOT EXISTS fukuda_mistakes(fingerprint TEXT, source_id TEXT, failures INTEGER, status TEXT)")
    repository.db.execute("INSERT INTO fukuda_mistakes VALUES ('source-1','note-1',1,'wrong')")
    repository.db.commit()
    repository.reset_piece("source-1")
    assert len(ledger.recent("source-1", "stage-1").recent) == 1
    assert repository.db.execute("SELECT kind FROM learning_events WHERE kind='progress_reset'").fetchall() == [("progress_reset",)]
    ledger.delete_piece("source-1")
    for table in ("learning_attempts", "learning_assessments", "learning_attempt_details", "learning_decisions", "learning_outcomes", "learning_rules", "mastery", "fukuda_mistakes"):
        assert repository.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
    assert not ledger.recent("source-1", "stage-1").recent
    assert not repository.db.execute("PRAGMA foreign_key_check").fetchall()


def test_delete_learner_rotates_identity_and_never_inherits_progress(repository, tmp_path):
    ledger = repository.ledger
    old = ledger.learner_id
    start(ledger)
    repository.db.execute("INSERT INTO mastery VALUES ('source-1','stage-1',90)")
    repository.db.commit()
    new = ledger.delete_learner()
    assert new and new != old and ledger.learner_id == new
    assert not ledger.status()["attempts"]
    assert repository.db.execute("SELECT count(*) FROM mastery").fetchone()[0] == 0
    reopened = ProgressRepository(tmp_path / "progress.db")
    try:
        assert reopened.ledger.learner_id == new
        assert reopened.db.execute("SELECT count(*) FROM learning_sessions").fetchone()[0] == 0
    finally:
        reopened.close()


def make_legacy(path):
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE practice_evidence(id INTEGER PRIMARY KEY, fingerprint TEXT, stage_key TEXT, bpm REAL, statuses TEXT, extra_notes INTEGER)")
    db.execute("INSERT INTO practice_evidence VALUES (4,'legacy-source','legacy-stage',80,'[\"correct\",\"late\"]',0)")
    db.execute("INSERT INTO practice_evidence VALUES (9,'legacy-source','legacy-stage',90,'[\"wrong\"]',1)")
    db.execute("CREATE TABLE mastery(fingerprint TEXT, exercise TEXT, bpm INTEGER, PRIMARY KEY(fingerprint,exercise))")
    db.execute("INSERT INTO mastery VALUES ('legacy-source','old-stage',90)")
    db.commit()
    db.close()


def test_migration_is_once_deterministic_unknown_and_preserves_saved_progress(tmp_path):
    path = tmp_path / "legacy.db"
    make_legacy(path)
    repository = ProgressRepository(path)
    assert hasattr(repository, "ledger"), "old bounded evidence must migrate into the ledger"
    try:
        ledger = repository.ledger
        assert [e.bpm for e in ledger.recent("legacy-source", "legacy-stage").recent] == [80., 90.]
        rows = repository.db.execute("SELECT attempt_id,provenance,ended_utc FROM learning_attempts ORDER BY attempt_id").fetchall()
        assert len(rows) == 2 and all(row[1:] == ("legacy_bounded", None) for row in rows)
        assert repository.db.execute("SELECT passed FROM learning_assessments").fetchall() == [(None,), (None,)]
        assert repository.db.execute("SELECT bpm FROM mastery").fetchone() == (90,)
        assert repository.db.execute("SELECT name FROM sqlite_master WHERE name='practice_evidence'").fetchone() is None
        assert repository.db.execute("PRAGMA user_version").fetchone()[0] >= 1
    finally:
        repository.close()
    reopened = ProgressRepository(path)
    try:
        assert reopened.db.execute("SELECT attempt_id,provenance,ended_utc FROM learning_attempts ORDER BY attempt_id").fetchall() == rows
    finally:
        reopened.close()


def test_migration_drop_failure_rolls_back_every_import_and_retries(tmp_path, monkeypatch):
    path = tmp_path / "legacy.db"
    make_legacy(path)
    connect = sqlite3.connect

    def refusing_connection(*args, **kwargs):
        db = connect(*args, **kwargs)
        db.set_authorizer(lambda action, name, *_: sqlite3.SQLITE_DENY
                          if action == sqlite3.SQLITE_DROP_TABLE and name == "practice_evidence"
                          else sqlite3.SQLITE_OK)
        return db

    monkeypatch.setattr(sqlite3, "connect", refusing_connection)
    with pytest.raises(sqlite3.DatabaseError):
        ProgressRepository(path)
    monkeypatch.undo()
    db = connect(path)
    assert db.execute("SELECT count(*) FROM practice_evidence").fetchone()[0] == 2
    assert db.execute("SELECT count(*) FROM sqlite_master WHERE name='learning_attempts'").fetchone()[0] == 0
    assert db.execute("PRAGMA user_version").fetchone()[0] == 0
    db.close()
    repository = ProgressRepository(path)
    try:
        assert len(repository.ledger.recent("legacy-source", "legacy-stage").recent) == 2
    finally:
        repository.close()
