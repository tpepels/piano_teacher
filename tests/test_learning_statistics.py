"""Useful statistics from the canonical ledger, including unknown/pruned facts."""
import json

import pytest

from piano_teacher.progress_repository import ProgressRepository


@pytest.fixture
def ledger(tmp_path):
    repository = ProgressRepository(tmp_path / "progress.db")
    yield repository.ledger
    repository.close()


def begin(ledger, attempt, *, piece="piece", bpm=90, scope="full", start=1.0, extra_context=None):
    ledger.start_session("session", "run", "2026-01-01T10:00:00Z", "Europe/Lisbon")
    rule = ledger.store_rules({"mastery": "accepted-full-target-v1"})
    ledger.start_attempt(attempt, "session", {
        "fingerprint": piece, "stage_key": "stage", "rule_id": rule,
        "hand": "both", "scope": scope, "assistance": False,
        "from_beat": 0, "end_beat": 4, "performed_bpm": bpm,
        "monotonic_start": start, "started_utc": "2026-01-01T10:00:01Z", **(extra_context or {})})


def finish(ledger, attempt, *, passed=True, clean=False, eligible=True, end=5.0):
    ledger.settle_attempt(attempt, {
        "state": "completed", "reason": "deadline", "monotonic_end": end,
        "ended_utc": "2026-01-01T10:00:05Z", "assistance_used": False,
        "assessment": {"bpm": 90, "statuses": ["correct", "late", "correct"],
                       "extra_notes": 0, "passed": passed, "clean": clean,
                       "mastery_eligible": eligible},
        "observations": [{"onset_residual": -.02, "duration_residual": None,
                          "pitch_error": False, "timing_error": None, "hold_error": None},
                         {"onset_residual": .04, "duration_residual": -.1,
                          "pitch_error": False, "timing_error": "late", "hold_error": "short"}]})


def test_statistics_separate_accepted_clean_eligible_and_measured_exposure(ledger):
    from piano_teacher.learning_statistics import learning_statistics
    begin(ledger, "first")
    finish(ledger, "first")
    begin(ledger, "repeat", start=7.0)
    finish(ledger, "repeat", passed=False, eligible=True, end=10.0)
    begin(ledger, "guided", piece="other", scope="guided", bpm=60)
    ledger.settle_attempt("guided", {"state": "aborted", "reason": "stop"})
    ledger.record_event("session", "phase_intervals", {"intervals": [
        {"phase": "practice", "start": 0, "end": 12},
        {"phase": "paused", "start": 12, "end": 17}]})
    changes_before = ledger.db.total_changes
    result = learning_statistics(ledger)
    assert ledger.db.total_changes == changes_before
    assert result["sessions"]["count"] == 1
    assert result["attempts"]["count"] == 3
    assert result["attempts"]["repetitions"] == 1
    assert result["assessments"]["accepted"] == 1
    assert result["assessments"]["strict_clean"] == 0
    assert result["assessments"]["mastery_eligible"] == 2
    assert result["assessments"]["accepted_mastery_eligible"] == 1
    assert result["assessments"]["accepted_with_warnings"] == 1
    assert result["mistakes"]["status_counts"] == {"correct": 4, "late": 2}
    assert result["timing"]["onset"]["sample_count"] == 4
    assert result["timing"]["onset"]["mean_seconds"] == pytest.approx(.01)
    assert result["timing"]["duration"]["sample_count"] == 2
    assert result["timing"]["independent_flags"]["hold_short"] == 2
    assert result["durations"]["phase_seconds"] == {"practice": 12.0, "paused": 5.0}
    assert result["durations"]["measured_attempt_seconds"] == 7.0
    piece = learning_statistics(ledger, "piece")
    assert piece["attempts"]["count"] == 2
    assert piece["durations"]["phase_seconds"] is None
    assert piece["durations"]["phase_missingness"] == "piece_attribution_unavailable"
    # Analytics must never mutate or award progress.
    assert ledger.db.execute("SELECT COUNT(*) FROM learning_attempts").fetchone()[0] == 3


def test_intervention_outcomes_require_actual_compatible_context_not_claims(ledger):
    from piano_teacher.learning_statistics import learning_statistics
    begin(ledger, "before")
    finish(ledger, "before", passed=False)
    ledger.add_decision("decision", "session", "before", {
        "policy": "repeat", "trigger": "full_take", "before_bpm": 90, "after_bpm": 72})
    begin(ledger, "slower", bpm=72)
    finish(ledger, "slower", clean=True)
    ledger.record_outcome("slower-outcome", "decision", "slower", {
        "kind": "proximal", "state": "completed", "passed": True,
        "comparability": {"source_and_stage": True, "tempo": True, "scope": True, "support": True}})
    begin(ledger, "same")
    finish(ledger, "same", clean=True)
    ledger.record_outcome("same-outcome", "decision", "same", {
        "kind": "episode_verification", "state": "completed", "passed": True})
    ledger.record_outcome("censored", "decision", None, {
        "kind": "proximal", "state": "censored", "reason": "navigation"})
    result = learning_statistics(ledger)
    assert result["interventions"]["decisions"] == 1
    assert result["interventions"]["policies"] == {"repeat": 1}
    assert result["interventions"]["outcomes"] == 3
    assert result["interventions"]["compatible_outcomes"] == 1
    assert result["interventions"]["incompatible_outcomes"] == 1
    assert result["interventions"]["censored_outcomes"] == 1
    assert result["interventions"]["compatible_accepted_outcomes"] == 1
    assert result["interventions"]["causal_comparison"] is False
    assert result["tempo"]["recorded_changes"] == 1
    assert result["tempo"]["reductions"] == 1


def test_pruned_legacy_and_crash_unknowns_survive_without_invented_zeroes(ledger):
    from piano_teacher.learning_statistics import learning_statistics
    begin(ledger, "first")
    finish(ledger, "first")
    ledger.close_session("session", "shutdown")
    ledger.prune(days=7, budget_mib=16, now_utc="2040-01-01T00:00:00Z")
    # Import the exact old retained-window schema; legacy pass/timing remain unknown.
    ledger.db.execute("CREATE TABLE practice_evidence(id INTEGER,fingerprint TEXT,stage_key TEXT,bpm REAL,statuses TEXT,extra_notes INTEGER)")
    ledger.db.execute("INSERT INTO practice_evidence VALUES (1,'piece','stage',80,?,0)", (json.dumps(["correct"]),))
    ledger.migrate_legacy()
    result = learning_statistics(ledger, "piece")
    assert result["attempts"]["count"] == 2
    assert result["assessments"]["accepted"] == 1
    assert result["assessments"]["acceptance_unknown"] == 1
    assert result["mistakes"]["status_counts"] == {"correct": 3, "late": 1}
    assert result["timing"]["onset"]["mean_seconds"] is None
    assert result["coverage"]["pruned_attempts"] == 1
    assert result["coverage"]["legacy_bounded_attempts"] == 1
    assert result["coverage"]["detail_history_complete"] is False
    assert result["durations"]["attempts_with_unknown_duration"] == 1
    assert result["durations"]["measured_attempt_seconds"] == 4.0
    assert learning_statistics(ledger, "never-seen")["assessments"]["acceptance_rate"] is None
    with pytest.raises(ValueError):
        learning_statistics(ledger, "")
