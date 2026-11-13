"""The embedded command boundary exposes measured learning, without HTTP."""
import json
import pytest

from test_mastery_acceptance_contract import practice_factory, _play
from piano_teacher.inprocess import EngineCommands, OK, INVALID


def test_versioned_statistics_queries_and_lock_free_formatting(practice_factory, monkeypatch):
    import threading
    from piano_teacher import learning_statistics_metrics
    engine, clock = practice_factory()
    _play(engine, clock)
    entered, release = threading.Event(), threading.Event()
    real = learning_statistics_metrics.extend_report
    def slow(*args):
        entered.set()
        assert release.wait(3)
        return real(*args)
    monkeypatch.setattr(learning_statistics_metrics, "extend_report", slow)
    result = []
    thread = threading.Thread(target=lambda: result.append(EngineCommands(engine=engine).request(
        "learning.statistics", json.dumps({"version": 1, "limit": 1}))))
    thread.start()
    assert entered.wait(3)
    try:
        assert engine.lock.acquire(timeout=.2), "Statistics formatting held the musical engine lock"
        engine.lock.release()
        _play(engine, clock)
        assert engine.plan.streak == 2
    finally:
        release.set()
        thread.join(3)
    assert result[0][0] == OK, result
    assert json.loads(result[0][1])["assessments"]["accepted"] == 1


def test_deleted_history_cannot_publish_while_report_formats(practice_factory, monkeypatch):
    from piano_teacher import learning_statistics_metrics
    engine, clock = practice_factory()
    _play(engine, clock)
    real = learning_statistics_metrics.extend_report
    def delete_then_format(*args):
        engine.progress.ledger.delete_piece(engine.fingerprint)
        return real(*args)
    monkeypatch.setattr(learning_statistics_metrics, "extend_report", delete_then_format)
    code, raw = EngineCommands(engine=engine).request("learning.statistics")
    assert code == INVALID, raw
    assert "changed" in json.loads(raw)["error"]


def test_snapshot_read_does_not_block_real_grading_commit(practice_factory, monkeypatch):
    import threading
    from piano_teacher import learning_statistics_query
    engine, clock = practice_factory()
    _play(engine, clock)
    entered, release, written = threading.Event(), threading.Event(), threading.Event()
    real = learning_statistics_query.capture_statistics
    def held_snapshot(*args):
        result = real(*args)
        entered.set()
        assert release.wait(3)
        return result
    monkeypatch.setattr(learning_statistics_query, "capture_statistics", held_snapshot)
    reader = threading.Thread(target=engine.learning_statistics)
    reader.start()
    assert entered.wait(3)
    def perform():
        _play(engine, clock)
        written.set()
    writer = threading.Thread(target=perform)
    writer.start()
    try:
        assert written.wait(.25), "The read snapshot blocked the canonical grading commit"
    finally:
        release.set()
        reader.join(3)
        writer.join(3)
    assert engine.plan.streak == 2


@pytest.mark.parametrize("policy", ["adaptive", "steady-repeat", "slow-practice", "micro-loop", "guided-repair", "finish-then-review"])
def test_authentic_six_policy_capture_keeps_resolved_strata_and_censoring(practice_factory, policy):
    engine, clock = practice_factory(attacks=tuple((i*.5, (60+i,)) for i in range(8)))
    engine.set_preferences(mistake_response_strategy=policy)
    engine.start()
    clock[0] = engine.visual_transport.run_at+4.21
    engine._update()
    if engine.pending_result is not None:
        engine._commit_pending()
    engine.control("stop")
    r = engine.learning_statistics()
    comparison = r["fixed_policy_comparison"]
    assert len(comparison["policies"]) == 6
    selected = next(p for p in comparison["policies"] if p["policy_id"] == policy)
    assert selected["decisions"] >= 1
    assert selected["cohorts"][0]["policy_parameters"]["policy_id"] == policy
    assert selected["cohorts"][0]["expertise"] is None
    assert selected["cohorts"][0]["proximal"]["censored"] >= 1
    assert selected["cohorts"][0]["proximal"]["assessed_denominator"] == 0
    assert comparison["causal_comparison"] is False


def test_authentic_mastery_projection_uses_recorded_award_and_target(practice_factory):
    from test_mastery_acceptance_contract import _accepted_warning
    engine, clock = practice_factory()
    for _ in range(3):
        _accepted_warning(engine, clock)
    episodes = engine.learning_statistics()["mastery"]["episodes"]
    mastered = next(e for e in episodes if e["mastered"])
    assert mastered["target_bpm"] == 60
    assert mastered["required_accepted_runs"] == 3
    assert mastered["attempts_to_mastery"] == 3
    assert mastered["accepted_eligible_attempts"] == 3


@pytest.mark.parametrize("scope", ["perform", "section_review"])
def test_typed_query_accepts_actual_perform_and_section_review_capture(practice_factory, scope):
    engine, clock = practice_factory()
    if scope == "section_review":
        engine.review_end_beat = 2.
    engine.start(mode="perform" if scope == "perform" else "practice")
    clock[0] = engine.visual_transport.run_at+(2. if scope == "section_review" else 4.)+.21
    engine._update()
    code, raw = EngineCommands(engine=engine).request("learning.statistics", json.dumps({"scope": scope}))
    assert code == OK, raw
    report = json.loads(raw)
    assert report["attempts"]["scopes"] == {scope: 1}
    assert report["assessments"]["mastery_eligible"] == 0


def test_typed_mastery_after_authentic_restart_with_restored_streak_is_censored(practice_factory):
    from test_mastery_acceptance_contract import _accepted_warning
    from piano_teacher.learning import LearningPlan
    from piano_teacher.server import PracticeEngine
    engine, clock = practice_factory()
    _accepted_warning(engine, clock)
    _accepted_warning(engine, clock)
    assert engine.plan.streak == 2
    piece, fingerprint, data_dir = engine.plan.piece, engine.fingerprint, engine._data_dir
    previous_session = engine.measurement.session_id
    engine.close()
    restarted = PracticeEngine(data_dir, enable_midi=False)
    try:
        restarted.plan = LearningPlan(piece, exercise_strategy="source-progression")
        restarted.fingerprint = fingerprint
        restarted.progress.restore(restarted.plan, fingerprint)
        assert restarted.plan.streak == 2
        assert restarted.measurement.session_id != previous_session
        restarted.midi.port = object()
        restarted.midi.device = "Deterministic test piano"
        _accepted_warning(restarted, clock)
        code, raw = EngineCommands(engine=restarted).request("learning.statistics")
        assert code == OK, raw
        mastered = next(e for e in json.loads(raw)["mastery"]["episodes"] if e["mastered"])
        assert mastered["attempts_observed"] == 1
        assert mastered["left_censored"] is True
        assert mastered["attempts_to_mastery"] is None
        assert mastered["active_seconds_to_mastery"] is None
    finally:
        restarted.listen.cancel()
        restarted.close()


def test_read_connection_releases_snapshot_before_format_and_closes_on_error(practice_factory, monkeypatch):
    import sqlite3
    from piano_teacher import learning_statistics_metrics
    engine, clock = practice_factory()
    _play(engine, clock)
    connections, closed = [], []
    original_connect = sqlite3.connect
    class Probe(sqlite3.Connection):
        def close(self):
            closed.append(self)
            super().close()
    def connect(*args, **kwargs):
        connection = original_connect(*args, **kwargs, factory=Probe)
        connections.append(connection)
        return connection
    original_format = learning_statistics_metrics.extend_report
    def format_report(*args):
        assert not connections[-1].in_transaction
        assert connections[-1].execute("PRAGMA query_only").fetchone()[0] == 1
        assert connections[-1].total_changes == 0
        return original_format(*args)
    monkeypatch.setattr(sqlite3, "connect", connect)
    monkeypatch.setattr(learning_statistics_metrics, "extend_report", format_report)
    changes = engine.db.total_changes
    engine.learning_statistics()
    assert connections == closed
    def fail(*_args):
        raise RuntimeError("projection failed")
    monkeypatch.setattr(learning_statistics_metrics, "extend_report", fail)
    with pytest.raises(RuntimeError, match="projection failed"):
        engine.learning_statistics()
    assert connections == closed
    assert engine.db.total_changes == changes


def test_statistics_command_distinguishes_warning_acceptance_and_strict_clean(practice_factory):
    engine, clock = practice_factory()
    _play(engine, clock, late=(1,))
    commands = EngineCommands(engine=engine)
    code, raw = commands.request("learning.statistics", json.dumps({"fingerprint": engine.fingerprint}))
    assert code == OK, raw
    report = json.loads(raw)
    assert report["assessments"]["accepted"] == 1
    assert report["assessments"]["strict_clean"] == 0
    assert report["assessments"]["accepted_mastery_eligible"] == 1
    assert report["mistakes"]["status_counts"]["late"] == 1
    assert engine.plan.streak == 1
    for payload in ({"fingerprint": ""}, {"fingerprint": 1}, {"unexpected": True}):
        assert commands.request("learning.statistics", json.dumps(payload))[0] == INVALID
