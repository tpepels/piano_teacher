import json
import pytest
from test_learning_statistics import ledger, begin, finish


def test_bounded_versioned_stable_pages_and_filters(ledger):
    from piano_teacher.learning_statistics import learning_statistics
    for i in range(7):
        begin(ledger, f"take-{i}", bpm=90 if i % 2 == 0 else 60)
        finish(ledger, f"take-{i}")
    page = learning_statistics(ledger, query={"limit": 2, "bpm_min": 90})
    assert page["schema_version"] == 2
    assert page["attempts"]["count"] == 2
    assert page["query"]["has_more"]
    ids = page["query"]["attempt_ids"]
    begin(ledger, "newer")
    finish(ledger, "newer")
    next_page = learning_statistics(ledger, query={"limit": 2, "bpm_min": 90, "cursor": page["query"]["next_cursor"]})
    assert len(set(ids + next_page["query"]["attempt_ids"])) == 4
    assert "newer" not in next_page["query"]["attempt_ids"]
    assert not next_page["query"]["has_more"]


@pytest.mark.parametrize("replace_boundary", [False, True])
def test_cursor_expires_when_tail_boundary_is_deleted_or_rowid_reused(replace_boundary):
    import sqlite3
    from piano_teacher.learning_ledger import LearningLedger
    from piano_teacher.learning_statistics import learning_statistics
    with sqlite3.connect(":memory:") as db:
        ledger = LearningLedger(db)
        for i in range(4):
            begin(ledger, f"old-{i}", piece="keep" if i < 2 else "tail")
            finish(ledger, f"old-{i}")
        page = learning_statistics(ledger, query={"limit": 1})
        assert page["query"]["attempt_ids"] == ["old-0"]
        assert page["query"]["high_water_sequence"] == 4
        ledger.delete_piece("tail")
        if replace_boundary:
            for i in range(2):
                begin(ledger, f"new-{i}", piece="new")
                finish(ledger, f"new-{i}")
            assert db.execute("SELECT attempt_id FROM learning_attempts WHERE rowid=4").fetchone() == ("new-1",)
        assert db.execute("SELECT attempt_id FROM learning_attempts WHERE rowid=1").fetchone() == ("old-0",)
        with pytest.raises(ValueError, match="expired statistics cursor"):
            learning_statistics(ledger, query={"limit": 1, "cursor": page["query"]["next_cursor"]})


@pytest.mark.parametrize("scope", ["perform", "section_review"])
def test_query_supports_authoritative_captured_nonmastery_scopes(ledger, scope):
    from piano_teacher.learning_statistics import learning_statistics
    begin(ledger, "take", scope=scope)
    finish(ledger, "take", eligible=False)
    report = learning_statistics(ledger, query={"scope": scope})
    assert report["attempts"]["count"] == 1
    assert report["attempts"]["scopes"] == {scope: 1}
    assert report["assessments"]["mastery_eligible"] == 0


@pytest.mark.parametrize("query", [{"limit": True}, {"limit": 1001}, {"bpm_min": True}, {"date_from": "2026-02-30"}, {"cursor": "bad"}, {"hand": "nose"}, {"version": 9}, {"extra": 1}])
def test_query_rejects_invalid_contract(ledger, query):
    from piano_teacher.learning_statistics import learning_statistics
    with pytest.raises(ValueError):
        learning_statistics(ledger, query=query)


def test_pitch_residual_context_and_error_exposures(ledger):
    from piano_teacher.learning_statistics import learning_statistics
    begin(ledger, "take")
    ledger.settle_attempt("take", {"state": "completed", "reason": "deadline", "monotonic_end": 5,
        "assessment": {"bpm": 90, "statuses": ["late", "wrong", "missed"], "extra_notes": 1, "passed": False, "clean": False, "mastery_eligible": True},
        "observations": [
            {"source_id": "a", "source_beat": 0, "source_measure": 1, "authored_hand": "right", "onset_group_id": "g", "status": "late", "omitted": False, "pitch_error": False, "onset_residual": .2},
            {"source_id": "b", "status": "wrong", "omitted": False, "pitch_error": True, "onset_residual": -.1},
            {"source_id": "c", "status": "missed", "omitted": True, "pitch_error": None}]})
    result = learning_statistics(ledger)
    assert result["pitch"]["assessed_obligations"] == 3
    assert result["pitch"]["correct_required_pitches"] == 1
    assert result["pitch"]["accuracy"] == pytest.approx(1/3)
    assert result["pitch"]["wrong"] == result["pitch"]["omitted"] == result["pitch"]["extra"] == 1
    assert result["timing"]["onset"]["quantiles_seconds"]["p50"] == pytest.approx(.05)
    assert result["timing"]["contexts"][0]["performed_bpm"] == 90
    assert result["errors"]["source_notes"][0]["exposures"] == 1
    assert result["assessment_strata"][0]["accepted_denominator"] == 1


def test_detail_budget_and_piece_phase_intersection(ledger):
    from piano_teacher.learning_statistics import learning_statistics
    begin(ledger, "take", start=2)
    finish(ledger, "take", end=5)
    ledger.record_event("session", "phase_intervals", {"intervals": [{"phase": "practice", "start": 0, "end": 4}, {"phase": "paused", "start": 4, "end": 9}]})
    report = learning_statistics(ledger, "piece", query={"detail_budget_bytes": 1})
    assert report["coverage"]["detail_budget_truncated_attempts"] == 1
    assert report["pitch"]["accuracy"] is None
    report = learning_statistics(ledger, "piece")
    assert report["durations"]["attributed_phase_seconds"] == {"practice": 2, "paused": 1}
    assert report["durations"]["active_practice_seconds"] == 2


def test_source_date_stage_hand_scope_session_policy_filters_and_deleted_cursor(ledger):
    from piano_teacher.learning_statistics import learning_statistics
    begin(ledger, "selected")
    finish(ledger, "selected")
    begin(ledger, "next")
    finish(ledger, "next")
    begin(ledger, "other", piece="other", scope="partial")
    finish(ledger, "other")
    for attempt in ("selected", "next"):
        ledger.add_decision(attempt+"-policy", "session", attempt, {"policy": "steady-repeat"})
    q = dict(fingerprint="piece", session_id="session", date_from="2026-01-01", date_to="2026-01-01",
             stage_key="stage", hand="both", scope="full", bpm_min=90, bpm_max=90, policy="steady-repeat", limit=1)
    report = learning_statistics(ledger, query=q)
    assert report["query"]["attempt_ids"] == ["selected"]
    assert learning_statistics(ledger, query={**q, "date_from": "2026-01-02", "date_to": "2026-01-03"})["attempts"]["count"] == 0
    cursor = report["query"]["next_cursor"]
    with pytest.raises(ValueError):
        learning_statistics(ledger, query={**q, "hand": "left", "cursor": cursor})
    ledger.delete_piece("piece")
    with pytest.raises(ValueError):
        learning_statistics(ledger, query={**q, "cursor": cursor})


def test_phase_union_and_unobserved_gaps_are_qualified(ledger):
    from piano_teacher.learning_statistics import learning_statistics
    begin(ledger, "take", start=2)
    finish(ledger, "take", end=8)
    ledger.record_event("session", "phase_intervals", {"intervals": [
        {"phase": "active", "start": 1, "end": 4},
        {"phase": "active", "start": 3, "end": 5},
        {"phase": "pause", "start": 5, "end": 6}]})
    report = learning_statistics(ledger)
    assert report["durations"]["active_practice_seconds"] == 3
    assert report["durations"]["attributed_phase_seconds"]["pause"] == 1
    assert report["durations"]["attempts_with_incomplete_phase_coverage"] == 1


def test_phase_window_without_any_overlapping_interval_is_unknown(ledger):
    from piano_teacher.learning_statistics import learning_statistics
    begin(ledger, "take", start=10)
    finish(ledger, "take", end=15)
    ledger.record_event("session", "phase_intervals", {"intervals": [{"phase": "active", "start": 0, "end": 5}]})
    report = learning_statistics(ledger)
    assert report["durations"]["active_practice_seconds"] is None
    assert report["durations"]["phase_unknown_attempts"] == 1


def test_interrupted_prefix_is_not_a_comparable_full_target_baseline(ledger):
    from piano_teacher.learning_statistics import learning_statistics
    begin(ledger, "prefix")
    ledger.settle_attempt("prefix", {"state": "interrupted", "reason": "rolling_recovery", "assessed_end_beat": 2,
        "assessment": {"bpm": 90, "statuses": ["missed"], "extra_notes": 0, "passed": False, "clean": False, "mastery_eligible": False}})
    ledger.add_decision("decision", "session", "prefix", {"policy": "steady-repeat"})
    begin(ledger, "full")
    finish(ledger, "full")
    ledger.record_outcome("verification", "decision", "full", {"kind": "episode_verification", "state": "completed"})
    report = learning_statistics(ledger)
    assert report["interventions"]["incompatible_outcomes"] == 1
    assert report["interventions"]["compatible_assessed_outcomes"] == 0


def test_mastery_reads_award_and_censors_unfinished_without_inference(ledger):
    from piano_teacher.learning_statistics import learning_statistics
    for name in ("first", "second", "third"):
        begin(ledger, name)
        finish(ledger, name)
    report = learning_statistics(ledger)
    assert report["mastery"]["episodes"][0]["mastered"] is False
    assert report["mastery"]["censored_episodes"] == 1
    ledger.record_event("session", "progression", {"mastery_transition": True}, attempt_id="third")
    report = learning_statistics(ledger)
    assert report["mastery"]["episodes"][0]["mastered"] is True
    assert report["mastery"]["episodes"][0]["attempts_to_mastery"] is None  # target was never captured


@pytest.mark.parametrize("session_filter", [False, True])
def test_mastery_award_after_cross_session_streak_is_left_censored(ledger, session_filter):
    from piano_teacher.learning_statistics import learning_statistics
    rule = ledger.store_rules({"mastery": "accepted-full-target-v1", "lesson_settings": {"clean_runs_to_master": 3}})
    for session, names in (("before-restart", ("first", "second")), ("after-restart", ("third",))):
        ledger.start_session(session, session+"-run", "2026-01-01T10:00:00Z", "UTC")
        for i, name in enumerate(names):
            ledger.start_attempt(name, session, {"fingerprint": "piece", "stage_key": "stage", "rule_id": rule,
                "hand": "both", "scope": "full", "assistance": False, "from_beat": 0, "end_beat": 4,
                "performed_bpm": 90, "target_bpm": 90, "monotonic_start": i*10,
                "started_utc": "2026-01-01T10:00:01Z"})
            finish(ledger, name, end=i*10+4)
        ledger.record_event(session, "phase_intervals", {"intervals": [{"phase": "active", "start": 0, "end": 20}]})
    ledger.record_event("after-restart", "progression", {"mastery_transition": True}, attempt_id="third")
    q = {"session_id": "after-restart"} if session_filter else {}
    report = learning_statistics(ledger, query=q)
    mastered = next(e for e in report["mastery"]["episodes"] if e["mastered"])
    assert mastered["attempts_observed"] == 1
    assert mastered["active_seconds_observed"] == 4
    assert mastered["left_censored"] is True
    assert mastered["attempts_to_mastery"] is None
    assert mastered["active_seconds_to_mastery"] is None


def test_policy_rates_only_use_comparable_linked_full_exposures(ledger):
    from piano_teacher.learning_statistics import learning_statistics
    from piano_teacher.application.mistake_responses import resolve_mistake_policy, mistake_policy_facts
    measured_context = dict(tempo_map_hash="recorded-map", calibration_ms=0, midi_available=True)
    begin(ledger, "before", extra_context=measured_context)
    finish(ledger, "before", passed=False)
    ledger.add_decision("decision", "session", "before", {"policy": "steady-repeat",
        "parameters": mistake_policy_facts(resolve_mistake_policy("steady-repeat"))})
    for name, bpm, scope in (("same", 90, "full"), ("slower", 60, "full"), ("shorter", 90, "partial")):
        begin(ledger, name, bpm=bpm, scope=scope, extra_context=measured_context)
        finish(ledger, name)
        ledger.record_outcome(name+"-outcome", "decision", name, {"kind": "episode_verification", "state": "completed"})
    result = learning_statistics(ledger)
    policy = next(p for p in result["fixed_policy_comparison"]["policies"] if p["policy_id"] == "steady-repeat")
    outcomes = policy["cohorts"][0]["episode_verification"]
    assert outcomes["assessed_denominator"] == 1
    assert outcomes["accepted"] == 1
    assert outcomes["incompatible"] == 2
    assert policy["cohorts"][0]["expertise"] is None
    assert result["fixed_policy_comparison"]["causal_comparison"] is False


def test_supported_context_filter_has_indexed_plan_and_reopen_is_idempotent(ledger):
    from piano_teacher.learning_statistics import learning_statistics
    begin(ledger, "take")
    finish(ledger, "take")
    statements = []
    ledger.db.set_trace_callback(statements.append)
    learning_statistics(ledger, query=dict(fingerprint="piece", stage_key="stage", hand="both", bpm_min=80, bpm_max=100))
    ledger.db.set_trace_callback(None)
    statement = next(s for s in statements if s.startswith("SELECT t.rowid AS sequence"))
    plan = " ".join(str(row) for row in ledger.db.execute("EXPLAIN QUERY PLAN " + statement))
    assert "learning_attempt_statistics_context" in plan
    from pathlib import Path
    from piano_teacher.progress_repository import ProgressRepository
    path = Path(ledger.db.execute("PRAGMA database_list").fetchone()[2])
    reopened = ProgressRepository(path)
    assert reopened.db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert reopened.db.execute("SELECT count(*) FROM learning_attempts").fetchone()[0] == 1
    assert reopened.db.execute("SELECT count(*) FROM sqlite_master WHERE name='learning_attempt_statistics_context'").fetchone()[0] == 1
    reopened.close()


def test_different_policy_rule_hashes_share_only_equal_frozen_grading_contexts(ledger):
    from piano_teacher.learning_statistics import learning_statistics
    from piano_teacher.application.mistake_responses import resolve_mistake_policy, mistake_policy_facts
    ledger.start_session("session", "run", "2026-01-01T10:00:00Z", "UTC")
    for i, (policy, tolerance) in enumerate((("steady-repeat", .1), ("slow-practice", .1), ("adaptive", .2))):
        parameters = mistake_policy_facts(resolve_mistake_policy(policy))
        rule = ledger.store_rules({"schema_version": 1, "grader": "nearest-onset-v1", "mastery": "accepted-full-target-v1",
            "lesson_settings": {"grading_onset_tolerance_seconds": tolerance}, "generator": "frozen-fixture",
            "generator_version": 1, "retry_version": 1, "retry": parameters})
        name = f"arm-{i}"
        ledger.start_attempt(name, "session", {"fingerprint": "piece", "stage_key": "stage", "rule_id": rule,
            "hand": "both", "scope": "full", "assistance": False, "from_beat": 0, "end_beat": 4,
            "performed_bpm": 90, "target_bpm": 90, "monotonic_start": i*10})
        finish(ledger, name, passed=False)
        ledger.add_decision(name+"-decision", "session", name, {"policy": policy, "parameters": parameters})
    report = learning_statistics(ledger)
    groups = report["fixed_policy_comparison"]["grading_context_groups"]
    assert len(groups) == 2
    shared = next(g for g in groups if len(g["arms"]) == 2)
    assert {a["policy_id"] for a in shared["arms"]} == {"steady-repeat", "slow-practice"}
    assert len({a["rule_id"] for a in shared["arms"]}) == 2
    assert shared["expertise_matched"] is None


def test_observation_cap_keeps_unread_obligations_unknown(ledger):
    from piano_teacher.learning_statistics import learning_statistics
    begin(ledger, "dense")
    ledger.settle_attempt("dense", {"state": "completed", "reason": "deadline",
        "assessment": {"bpm": 90, "statuses": ["correct"]*10001, "extra_notes": 0,
                       "passed": True, "clean": True, "mastery_eligible": True},
        "observations": [{"omitted": False, "pitch_error": False}]*10001})
    report = learning_statistics(ledger)
    assert report["coverage"]["truncated_observations"] == 1
    assert report["pitch"]["assessed_obligations"] == 10000
    assert report["pitch"]["unknown_obligations"] == 1
    assert not report["coverage"]["detail_history_complete"]


def test_location_and_local_tempo_context_caps_are_explicit(ledger):
    from piano_teacher.learning_statistics import learning_statistics
    begin(ledger, "dense")
    ledger.settle_attempt("dense", {"state": "completed", "reason": "deadline",
        "assessment": {"bpm": 90, "statuses": ["correct"]*1001, "extra_notes": 0,
                       "passed": True, "clean": True, "mastery_eligible": True},
        "observations": [{"source_id": str(i), "omitted": False, "pitch_error": False,
                          "local_seconds_per_beat": .5+i/10000} for i in range(1001)]})
    report = learning_statistics(ledger)
    assert len(report["errors"]["source_notes"]) == 1000
    assert report["errors"]["omitted_location_obligations"]["source_notes"] == 1
    assert len(report["timing"]["contexts"]) == 250
    assert report["timing"]["context_truncated_observations"] == 751
    assert report["pitch"]["assessed_obligations"] == 1001


def test_phase_interval_cap_is_explicit_and_duplicate_intervals_do_not_inflate_time(ledger):
    from piano_teacher.learning_statistics import learning_statistics
    begin(ledger, "take", start=0)
    finish(ledger, "take", end=2)
    ledger.record_event("session", "phase_intervals", {"intervals": [{"phase": "active", "start": 0, "end": 2}]*20001})
    report = learning_statistics(ledger)
    assert report["durations"]["truncated_phase_intervals"] == 1
    assert report["durations"]["active_practice_seconds"] == 2
    assert not report["coverage"]["detail_history_complete"]
