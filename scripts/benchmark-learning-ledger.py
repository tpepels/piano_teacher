#!/usr/bin/env python3
"""Bounded local storage/resource receipt; never opens a learner database."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sqlite3
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from piano_teacher.progress_repository import ProgressRepository


def run():
    with tempfile.TemporaryDirectory(prefix="piano-ledger-benchmark-") as folder:
        path = Path(folder)
        repo = ProgressRepository(path / "progress.db")
        ledger = repo.ledger
        ledger.start_session("dense", "benchmark", "2020-01-01T00:00:00Z", "UTC")
        rule = ledger.store_rules({"benchmark": 1, "mastery": "accepted-full-target-v1"})
        context = {"fingerprint": "synthetic-dense", "stage_key": "dense-256",
                   "scope": "full", "rule_id": rule, "performed_bpm": 90}
        notes = [{"source_id": f"source-{i}", "press_id": i,
                  "expected_pitch": 48+i%36, "actual_pitch": 48+i%36,
                  "expected_onset": i/8, "actual_onset": i/8+.01,
                  "expected_release": i/8+.1, "actual_release": i/8+.11,
                  "onset_residual": .01, "duration_residual": 0.0} for i in range(256)]
        terminal = {"state": "completed", "reason": "benchmark",
                    "assessment": {"bpm": 90, "statuses": ["correct"]*256,
                        "extra_notes": 0, "clean": True, "passed": True, "mastery_eligible": True},
                    "observations": notes, "played": [{"pitch": n["actual_pitch"],
                        "onset": n["actual_onset"], "release": n["actual_release"]} for n in notes]}
        began = time.perf_counter()
        for i in range(200):
            ledger.start_attempt(f"dense-{i}", "dense", context)
            ledger.settle_attempt(f"dense-{i}", terminal)
        settle_seconds = time.perf_counter()-began
        ledger.record_event("dense", "phase_intervals", {"intervals": [
            {"phase": "active", "start": i*600., "end": (i+1)*600.} for i in range(1000)]})
        ledger.close_session("dense", "benchmark_finished")
        repo.db.execute("UPDATE learning_sessions SET ended_utc='2020-01-01T01:00:00Z' WHERE session_id='dense'")
        ledger.start_session("pending", "benchmark", "2026-11-04T00:00:00Z", "UTC")
        ledger.start_attempt("pending", "pending", context)
        def authorizer(action, table, column, *unused):
            return (sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_READ and
                    table == "learning_attempt_details" else sqlite3.SQLITE_OK)
        repo.db.set_authorizer(authorizer)
        checkpoints = []
        try:
            for i in range(20):
                began = time.perf_counter()
                ledger.checkpoint("pending", {"boundary": i, "played": notes[:i]})
                checkpoints.append(time.perf_counter()-began)
        finally:
            repo.db.set_authorizer(None)
        before = ledger.status()
        began = time.perf_counter()
        ledger.export(path / "export.json", include_detail=True)
        export_seconds = time.perf_counter()-began
        physical_bytes = (path / "progress.db").stat().st_size
        after = ledger.prune(days=365, budget_mib=16, now_utc="2026-11-04T12:00:00Z")
        assert after["pruned_attempts"] == 200 and after["open_attempts"] == 1
        assert repo.db.execute("SELECT state FROM learning_attempts WHERE attempt_id='pending'").fetchone() == ("open",)
        result = {"schema_version": 1, "python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
            "fixture": {"settled_attempts": 200, "notes_per_attempt": 256, "note_observations": 51200,
                        "phase_intervals": 1000, "synthetic_active_hours": 1000/6, "checkpoints": 20},
            "settle_seconds": settle_seconds, "checkpoint_max_seconds": max(checkpoints),
            "checkpoint_history_detail_read_denied": True, "export_seconds": export_seconds,
            "logical_bytes_before": before["logical_detail_bytes"], "sqlite_file_bytes": physical_bytes,
            "logical_bytes_after": after["logical_detail_bytes"], "coverage_after": after["coverage"],
            "pending_preserved": True,
            "source_sha256": {f: hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in (
                "piano_teacher/learning_ledger.py", "piano_teacher/progress_repository.py",
                "scripts/benchmark-learning-ledger.py")},
            "limits": "Synthetic local storage only; timings are observations, not hardware, musical learning or clean-machine acceptance."}
        repo.close()
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps({key: report[key] for key in ("settle_seconds", "checkpoint_max_seconds",
        "export_seconds", "logical_bytes_before", "logical_bytes_after", "pending_preserved")}))
