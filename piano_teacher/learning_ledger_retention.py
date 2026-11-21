"""Retention owner for bounded detailed learning evidence.

Operates on the same SQLite connection and savepoints as the ledger; pruning
never deletes open/pending attempts or independent durable summaries.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
import json
import sqlite3

from .learning_ledger_common import LearningLedgerLimitError, _json, _utc
from .sqlite_transaction import sqlite_atomic


def scan_detail_bytes(db: sqlite3.Connection) -> int:
    expressions = (
        "SELECT coalesce(sum(coalesce(length(CAST(context_json AS BLOB)),0)+coalesce(length(CAST(checkpoint_json AS BLOB)),0)),0) FROM learning_attempts",
        "SELECT coalesce(sum(length(CAST(detail_json AS BLOB))),0) FROM learning_attempt_details",
        *(f"SELECT coalesce(sum(length(CAST(data_json AS BLOB))),0) FROM {table}" for table in ("learning_events", "learning_decisions", "learning_outcomes")),
    )
    return sum(db.execute(query).fetchone()[0] for query in expressions)


class LearningDetailRetention:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    @property
    def learner_id(self) -> str:
        return self.db.execute("SELECT learner_id FROM learning_current_learner WHERE singleton=1").fetchone()[0]

    def logical_detail_bytes(self) -> int:
        return self.db.execute("SELECT logical_bytes FROM learning_detail_usage WHERE singleton=1").fetchone()[0]

    def _prune_session(self, session_id):
        count = self.db.execute("SELECT count(*) FROM learning_attempts WHERE session_id=? AND detail_pruned=0 AND provenance='native'", (session_id,)).fetchone()[0]
        self.db.execute("DELETE FROM learning_attempt_details WHERE attempt_id IN (SELECT attempt_id FROM learning_attempts WHERE session_id=?)", (session_id,))
        self.db.execute("UPDATE learning_attempts SET context_json=NULL,checkpoint_json=NULL,detail_pruned=1 WHERE session_id=? AND provenance='native'", (session_id,))
        self.db.execute("UPDATE learning_events SET data_json=NULL WHERE session_id=?", (session_id,))
        self.db.execute("UPDATE learning_decisions SET data_json=NULL WHERE session_id=?", (session_id,))
        self.db.execute("UPDATE learning_outcomes SET data_json=NULL WHERE decision_id IN (SELECT decision_id FROM learning_decisions WHERE session_id=?)", (session_id,))
        self.db.execute("UPDATE learning_sessions SET detail_pruned=1 WHERE session_id=?", (session_id,))
        self._prune_status_sequences(session_id)
        return count

    def _prune_status_sequences(self, session_id=None):
        # Status order is per-note detail too. Keep counts/pass facts after
        # pruning, rather than allowing the old sequence to bypass retention.
        query = """SELECT a.attempt_id,a.statuses_json,a.summary_json
            FROM learning_assessments a JOIN learning_attempts t USING(attempt_id)
            WHERE t.detail_pruned=1 AND a.statuses_json<>'[]'"""
        if session_id is not None:
            query += " AND t.session_id=?"
        rows = self.db.execute(query, () if session_id is None else (session_id,)).fetchall()
        for attempt, encoded, summary_json in rows:
            statuses = json.loads(encoded)
            summary = json.loads(summary_json)
            summary.pop("statuses", None)
            summary.update(status_counts=dict(Counter(statuses)), note_count=len(statuses),
                           note_detail_pruned=True)
            self.db.execute("UPDATE learning_assessments SET statuses_json='[]',summary_json=? WHERE attempt_id=?",
                            (_json(summary), attempt))

    def _prune(self, days, budget_mib, now_utc=None):
        now = datetime.fromisoformat((now_utc or _utc()).replace("Z", "+00:00"))
        if now.tzinfo is None:
            raise ValueError("Retention requires a timezone-aware UTC timestamp")
        cutoff = (now - timedelta(days=days)).isoformat().replace("+00:00", "Z")
        candidates = self.db.execute("""SELECT session_id,coalesce(ended_utc,recovered_utc,started_utc)
            FROM learning_sessions s WHERE learner_id=? AND closure_reason IS NOT NULL AND detail_pruned=0
            AND closure_reason<>'legacy_bounded'
            AND NOT EXISTS (SELECT 1 FROM learning_attempts t WHERE t.session_id=s.session_id AND t.state='open')
            ORDER BY coalesce(ended_utc,recovered_utc,started_utc),session_id""", (self.learner_id,)).fetchall()
        pruned = 0
        for session_id, completed_utc in candidates:
            if (completed_utc is not None and completed_utc < cutoff) or self.logical_detail_bytes() > budget_mib * 1024 * 1024:
                pruned += self._prune_session(session_id)
        if self.logical_detail_bytes() > budget_mib * 1024 * 1024:
            raise LearningLedgerLimitError("The logical detail budget limit cannot fit open or pending evidence")
        return pruned

    def enforce_budget(self, *, recovering: bool = False):
        if recovering:
            return
        days, budget = self.db.execute("SELECT days,budget_mib FROM learning_retention WHERE singleton=1").fetchone()
        if self.logical_detail_bytes() > budget * 1024 * 1024:
            self._prune(days, budget)

    def prune(self, days=365, budget_mib=256, now_utc=None) -> dict:
        if (isinstance(days, bool) or not isinstance(days, int) or not 7 <= days <= 3650
                or isinstance(budget_mib, bool) or not isinstance(budget_mib, int) or not 16 <= budget_mib <= 4096):
            raise ValueError("Retention requires 7–3650 days and a 16–4096 MiB logical detail budget")
        with sqlite_atomic(self.db):
            self._prune_status_sequences()
            count = self._prune(days, budget_mib, now_utc)
            self.db.execute("UPDATE learning_retention SET days=?,budget_mib=? WHERE singleton=1", (days, budget_mib))
            return {"pruned_attempts": count, **self.status()}

    def status(self) -> dict:
        count = lambda table: self.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        days, budget = self.db.execute("SELECT days,budget_mib FROM learning_retention WHERE singleton=1").fetchone()
        bounds = self.db.execute("""SELECT min(s.started_utc),min(CASE WHEN t.detail_pruned=0 THEN s.started_utc END),
                sum(t.detail_pruned),sum(CASE WHEN t.provenance='legacy_bounded' THEN 1 ELSE 0 END)
                FROM learning_attempts t JOIN learning_sessions s USING(session_id)""").fetchone()
        censored = self.db.execute("SELECT summary_json FROM learning_outcomes").fetchall()
        pruned_sessions = self.db.execute("SELECT count(*) FROM learning_sessions WHERE detail_pruned=1").fetchone()[0]
        coverage = {"summary_retained_since_utc": bounds[0], "detail_retained_since_utc": bounds[1],
                    "pruned_detail_attempts": bounds[2] or 0, "legacy_bounded_attempts": bounds[3] or 0,
                    "pruned_detail_sessions": pruned_sessions,
                    "censored_outcomes": sum(json.loads(row[0]).get("state") == "censored" for row in censored),
                    "legacy_history_complete": False, "detail_history_complete": not bool(pruned_sessions or bounds[2] or bounds[3])}
        return {"learner_id": self.learner_id, "sessions": count("learning_sessions"),
                "attempts": count("learning_attempts"), "assessments": count("learning_assessments"),
                "open_attempts": self.db.execute("SELECT count(*) FROM learning_attempts WHERE state='open'").fetchone()[0],
                "logical_detail_bytes": self.logical_detail_bytes(), "detail_days": days,
                "detail_budget_mib": budget, "coverage": coverage}
