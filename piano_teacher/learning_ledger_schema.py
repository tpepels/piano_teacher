"""SQLite schema and detail-accounting triggers for learning evidence."""
from __future__ import annotations

import sqlite3

from .learning_ledger_retention import scan_detail_bytes


def create_ledger_schema(db: sqlite3.Connection) -> None:
    statements = (
        """CREATE TABLE IF NOT EXISTS learning_learners (
            learner_id TEXT PRIMARY KEY, created_utc TEXT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS learning_current_learner (
            singleton INTEGER PRIMARY KEY CHECK(singleton=1),
            learner_id TEXT NOT NULL REFERENCES learning_learners ON DELETE CASCADE)""",
        """CREATE TABLE IF NOT EXISTS learning_retention (
            singleton INTEGER PRIMARY KEY CHECK(singleton=1),
            days INTEGER NOT NULL, budget_mib INTEGER NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS learning_sessions (
            session_id TEXT PRIMARY KEY, learner_id TEXT NOT NULL REFERENCES learning_learners ON DELETE CASCADE,
            run_id TEXT NOT NULL, started_utc TEXT, timezone TEXT,
            ended_utc TEXT, closure_reason TEXT, recovered_utc TEXT,
            start_hash TEXT NOT NULL, durations_json TEXT NOT NULL DEFAULT '{}',
            detail_pruned INTEGER NOT NULL DEFAULT 0)""",
        """CREATE TABLE IF NOT EXISTS learning_rules (
            rule_id TEXT PRIMARY KEY, snapshot_json TEXT NOT NULL, created_utc TEXT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS learning_attempts (
            attempt_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES learning_sessions ON DELETE CASCADE,
            fingerprint TEXT NOT NULL, stage_key TEXT NOT NULL,
            rule_id TEXT REFERENCES learning_rules,
            state TEXT NOT NULL DEFAULT 'open', reason TEXT, ended_utc TEXT,
            context_hash TEXT NOT NULL, terminal_hash TEXT,
            summary_json TEXT NOT NULL, context_json TEXT, checkpoint_json TEXT,
            detail_pruned INTEGER NOT NULL DEFAULT 0, provenance TEXT NOT NULL DEFAULT 'native')""",
        """CREATE TABLE IF NOT EXISTS learning_assessments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attempt_id TEXT NOT NULL UNIQUE REFERENCES learning_attempts ON DELETE CASCADE,
            bpm REAL NOT NULL, statuses_json TEXT NOT NULL, extra_notes INTEGER NOT NULL,
            assessed INTEGER NOT NULL DEFAULT 1, clean INTEGER, passed INTEGER,
            mastery_eligible INTEGER NOT NULL DEFAULT 0, summary_json TEXT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS learning_attempt_details (
            attempt_id TEXT PRIMARY KEY REFERENCES learning_attempts ON DELETE CASCADE,
            detail_json TEXT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS learning_events (
            event_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES learning_sessions ON DELETE CASCADE,
            attempt_id TEXT REFERENCES learning_attempts ON DELETE CASCADE,
            fingerprint TEXT, kind TEXT NOT NULL, payload_hash TEXT NOT NULL,
            summary_json TEXT NOT NULL, data_json TEXT)""",
        """CREATE TABLE IF NOT EXISTS learning_decisions (
            decision_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES learning_sessions ON DELETE CASCADE,
            attempt_id TEXT REFERENCES learning_attempts ON DELETE CASCADE,
            fingerprint TEXT, payload_hash TEXT NOT NULL, summary_json TEXT NOT NULL, data_json TEXT)""",
        """CREATE TABLE IF NOT EXISTS learning_outcomes (
            outcome_id TEXT PRIMARY KEY, decision_id TEXT NOT NULL REFERENCES learning_decisions ON DELETE CASCADE,
            attempt_id TEXT REFERENCES learning_attempts ON DELETE CASCADE,
            payload_hash TEXT NOT NULL, summary_json TEXT NOT NULL, data_json TEXT)""",
        """CREATE INDEX IF NOT EXISTS learning_session_time ON learning_sessions(learner_id,started_utc)""",
        """CREATE INDEX IF NOT EXISTS learning_attempt_stage ON learning_attempts(fingerprint,stage_key,session_id)""",
        """CREATE INDEX IF NOT EXISTS learning_attempt_statistics_context ON learning_attempts(
            fingerprint,stage_key,json_extract(summary_json,'$.hand'),
            json_extract(summary_json,'$.performed_bpm'),json_extract(summary_json,'$.scope'),
            substr(json_extract(summary_json,'$.started_utc'),1,10))""",
        """CREATE INDEX IF NOT EXISTS learning_attempt_session ON learning_attempts(session_id,state)""",
        """CREATE INDEX IF NOT EXISTS learning_event_session ON learning_events(session_id,attempt_id)""",
        """CREATE INDEX IF NOT EXISTS learning_decision_attempt ON learning_decisions(attempt_id,session_id)""",
        """CREATE INDEX IF NOT EXISTS learning_outcome_decision ON learning_outcomes(decision_id,attempt_id)""",
        """CREATE INDEX IF NOT EXISTS learning_retained_status ON learning_assessments(attempt_id)
            WHERE statuses_json<>'[]'""",
    )
    for statement in statements:
        db.execute(statement)
    db.execute("INSERT OR IGNORE INTO learning_retention VALUES (1,365,256)")
    db.execute("""CREATE TABLE IF NOT EXISTS learning_detail_usage (
        singleton INTEGER PRIMARY KEY CHECK(singleton=1), logical_bytes INTEGER NOT NULL CHECK(logical_bytes>=0))""")
    if not db.execute("SELECT 1 FROM learning_detail_usage WHERE singleton=1").fetchone():
        db.execute("INSERT INTO learning_detail_usage VALUES (1,?)", (scan_detail_bytes(db),))
    # Accounting lives in SQLite so nested rollback, FK cascades and a
    # reopened connection retain the same byte total. Normal writes inspect
    # only their own changed payload, never every past note observation.
    for table, columns in (
            ("learning_attempts", ("context_json", "checkpoint_json")),
            ("learning_attempt_details", ("detail_json",)),
            *((name, ("data_json",)) for name in ("learning_events", "learning_decisions", "learning_outcomes"))):
        amount = lambda prefix: "+".join(f"coalesce(length(CAST({prefix}.{column} AS BLOB)),0)" for column in columns)
        new, old = amount("NEW"), amount("OLD")
        for suffix, event, change in (("insert", "INSERT", f"+({new})"),
                                      ("delete", "DELETE", f"-({old})"),
                                      ("update", "UPDATE OF " + ",".join(columns), f"+({new})-({old})")):
            db.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_usage_{suffix}
                AFTER {event} ON {table} BEGIN
                UPDATE learning_detail_usage SET logical_bytes=logical_bytes{change} WHERE singleton=1;
                END""")
