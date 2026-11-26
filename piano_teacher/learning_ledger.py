"""Connection-scoped transactional ledger of attempts and intervention facts.

The application owns IDs, musical timing and the connection. This boundary
records facts, not alternative grading or MIDI interpretations. Retention,
schema and export are distinct collaborators on the same SQLite connection.
"""
from __future__ import annotations
import math

from collections import Counter
from hashlib import sha256
import json
import sqlite3
from uuid import NAMESPACE_URL, uuid4, uuid5

from .learning_ledger_common import (
    SCHEMA_VERSION, _compact, _context_summary, _hash, _identifier, _json, _object, _utc,
)
from .learning_ledger_export import LearningHistoryExporter
from .learning_ledger_retention import LearningDetailRetention
from .learning_ledger_schema import create_ledger_schema
from .sqlite_transaction import sqlite_atomic


_PROGRESS_TABLES = ("strategy_sessions", "learner_units", "learner_stages",
                    "repeat_tempo_credit", "stage_tempos", "mastery", "sessions",
                    "fukuda_mistakes", "piece_progress")


class LearningLedger:
    """Connection-scoped evidence owner; all mutations compose with sqlite_atomic."""

    def __init__(self, db: sqlite3.Connection):
        self.db = db
        self._recovering = False
        self.retention = LearningDetailRetention(db)
        self.history_exporter = LearningHistoryExporter(db, self.retention)
        # ProgressRepository enables this before beginning migration. Standalone
        # use on a fresh connection gets the same relational protections.
        self.db.execute("PRAGMA foreign_keys=ON")
        with sqlite_atomic(db):
            create_ledger_schema(db)
            if not db.execute("SELECT 1 FROM learning_current_learner").fetchone():
                self._new_learner()

    @property
    def learner_id(self) -> str:
        return self.db.execute("SELECT learner_id FROM learning_current_learner WHERE singleton=1").fetchone()[0]

    def _new_learner(self) -> str:
        identity = str(uuid4())
        self.db.execute("INSERT INTO learning_learners VALUES (?,?)", (identity, _utc()))
        self.db.execute("INSERT OR REPLACE INTO learning_current_learner VALUES (1,?)", (identity,))
        return identity

    def start_session(self, session_id: str, run_id: str, started_utc: str, timezone: str):
        for value, label in ((session_id, "session ID"), (run_id, "run ID"), (started_utc, "UTC start"), (timezone, "timezone")):
            _identifier(value, label)
        facts = [self.learner_id, run_id, started_utc, timezone]
        with sqlite_atomic(self.db):
            prior = self.db.execute("SELECT start_hash FROM learning_sessions WHERE session_id=?", (session_id,)).fetchone()
            if prior:
                if prior[0] != _hash(facts):
                    raise ValueError("Conflicting session identity replay")
                return
            self.db.execute("""INSERT INTO learning_sessions
                (session_id,learner_id,run_id,started_utc,timezone,start_hash) VALUES (?,?,?,?,?,?)""",
                (session_id, *facts, _hash(facts)))

    def store_rules(self, snapshot: dict) -> str:
        encoded = _json(_object(snapshot, "rule snapshot"))
        identity = sha256(encoded.encode("utf-8")).hexdigest()
        with sqlite_atomic(self.db):
            self.db.execute("INSERT OR IGNORE INTO learning_rules VALUES (?,?,?)", (identity, encoded, _utc()))
        return identity

    def _session(self, session_id, *, require_open=True):
        _identifier(session_id, "session ID")
        row = self.db.execute("SELECT learner_id,closure_reason FROM learning_sessions WHERE session_id=?", (session_id,)).fetchone()
        if not row or row[0] != self.learner_id:
            raise ValueError("Unknown current learner session")
        if require_open and row[1] is not None:
            raise ValueError("The practice session is closed")

    def _attempt(self, attempt_id):
        _identifier(attempt_id, "attempt ID")
        row = self.db.execute("SELECT session_id,fingerprint,stage_key,state,terminal_hash FROM learning_attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
        if not row:
            raise ValueError("Unknown attempt identity")
        self._session(row[0], require_open=False)
        return row

    def start_attempt(self, attempt_id: str, session_id: str, context: dict):
        _identifier(attempt_id, "attempt ID")
        _object(context, "attempt context")
        fingerprint = _identifier(context.get("fingerprint"), "source fingerprint")
        stage_key = _identifier(context.get("stage_key"), "exact stage key")
        digest = _hash([session_id, context])
        with sqlite_atomic(self.db):
            prior = self.db.execute("SELECT context_hash FROM learning_attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            if prior:
                if prior[0] != digest:
                    raise ValueError("Conflicting attempt identity replay")
                return
            self._session(session_id)
            self.db.execute("""INSERT INTO learning_attempts
                (attempt_id,session_id,fingerprint,stage_key,rule_id,context_hash,summary_json,context_json)
                VALUES (?,?,?,?,?,?,?,?)""", (attempt_id, session_id, fingerprint, stage_key,
                    context.get("rule_id"), digest, _json(_context_summary(context)), _json(context)))
            self._enforce_budget()

    def discard_open_attempt(self, attempt_id: str, *, session_id: str) -> None:
        """Remove a non-learning exposure, including checkpointed evidence."""
        with sqlite_atomic(self.db):
            row = self._attempt(attempt_id)
            if row[0] != session_id or row[3] != "open" or row[4] is not None:
                raise ValueError("Only the current open attempt can be discarded")
            self.db.execute("DELETE FROM learning_attempts WHERE attempt_id=?",
                            (attempt_id,))

    def checkpoint(self, attempt_id: str, payload: dict):
        encoded = _json(_object(payload, "checkpoint"))
        with sqlite_atomic(self.db):
            row = self._attempt(attempt_id)
            if row[3] != "open":
                raise ValueError("A settled attempt cannot accept a checkpoint")
            self.db.execute("UPDATE learning_attempts SET checkpoint_json=? WHERE attempt_id=?", (encoded, attempt_id))
            self._enforce_budget()

    def settle_attempt(self, attempt_id: str, terminal: dict) -> bool:
        _object(terminal, "terminal payload")
        state = _identifier(terminal.get("state"), "terminal state")
        if state == "open":
            raise ValueError("Settlement requires a terminal state")
        _identifier(terminal.get("reason"), "terminal reason")
        digest = _hash(terminal)
        with sqlite_atomic(self.db):
            row = self._attempt(attempt_id)
            if row[4] is not None:
                if row[4] != digest:
                    raise ValueError("Conflicting terminal replay for an already settled attempt")
                return False
            assessment = terminal.get("assessment")
            if assessment is not None:
                self._insert_assessment(attempt_id, row[2], _object(assessment, "assessment"))
            summary = json.loads(self.db.execute("SELECT summary_json FROM learning_attempts WHERE attempt_id=?", (attempt_id,)).fetchone()[0])
            summary["terminal"] = _compact({key: value for key, value in terminal.items()
                if key not in {"assessment", "observations", "played", "checkpoint"}})
            self.db.execute("""UPDATE learning_attempts SET state=?,reason=?,ended_utc=?,
                terminal_hash=?,summary_json=?,checkpoint_json=NULL WHERE attempt_id=?""",
                (state, terminal["reason"], terminal.get("ended_utc"), digest, _json(summary), attempt_id))
            self.db.execute("INSERT INTO learning_attempt_details VALUES (?,?)", (attempt_id, _json(terminal)))
            self._enforce_budget()
            return True

    def _insert_assessment(self, attempt_id: str, stage_key: str, assessment: dict, *, legacy=False):
        statuses = assessment.get("statuses", [])
        bpm = assessment.get("bpm")
        extra = assessment.get("extra_notes", 0)
        if (not isinstance(statuses, (list, tuple)) or not statuses
                or isinstance(extra, bool) or not isinstance(extra, int)
                or isinstance(bpm, bool) or not isinstance(bpm, (float, int))):
            raise ValueError("An assessment needs actual statuses, positive BPM and extra-note count")
        allowed = {"correct", "early", "late", "short", "long", "missed", "wrong"}
        if (not stage_key or any(status not in allowed for status in statuses)
                or extra < 0 or not math.isfinite(bpm) or bpm <= 0):
            raise ValueError("Invalid graded assessment evidence")
        for field in ("clean", "passed", "mastery_eligible"):
            if not legacy and not isinstance(assessment.get(field), bool):
                raise ValueError(f"An assessment must explicitly record {field}")
        summary = {**_compact({k: v for k, v in assessment.items() if k != "statuses"}),
                   "status_counts": dict(Counter(statuses)), "note_count": len(statuses)}
        self.db.execute("""INSERT INTO learning_assessments
            (attempt_id,bpm,statuses_json,extra_notes,assessed,clean,passed,mastery_eligible,summary_json)
            VALUES (?,?,?,?,?,?,?,?,?)""", (attempt_id, bpm, _json(statuses), extra, 1,
                assessment.get("clean"), assessment.get("passed"), bool(assessment.get("mastery_eligible", False)), _json(summary)))

    def _linked_attempt(self, session_id, attempt_id, data):
        self._session(session_id)
        if attempt_id is None:
            return data.get("fingerprint")
        row = self._attempt(attempt_id)
        if row[0] != session_id:
            raise ValueError("An event or decision cannot cross practice sessions")
        return row[1]

    def _stable_insert(self, table, identity_column, identity, facts, columns, values):
        _identifier(identity)
        digest = _hash(facts)
        old = self.db.execute(f"SELECT payload_hash FROM {table} WHERE {identity_column}=?", (identity,)).fetchone()
        if old:
            if old[0] != digest:
                raise ValueError("Conflicting evidence identity replay")
            return False
        names = ",".join((identity_column, *columns, "payload_hash", "summary_json", "data_json"))
        data = facts[-1]
        arguments = (identity, *values, digest, _json(_compact(data)), _json(data))
        self.db.execute(f"INSERT INTO {table} ({names}) VALUES ({','.join('?' for _ in arguments)})", arguments)
        self._enforce_budget()
        return True

    def record_event(self, session_id, kind, data, *, attempt_id=None, event_id=None) -> str:
        _identifier(kind, "event kind")
        _object(data, "event data")
        identity = event_id or str(uuid4())
        with sqlite_atomic(self.db):
            fingerprint = self._linked_attempt(session_id, attempt_id, data)
            inserted = self._stable_insert("learning_events", "event_id", identity,
                [session_id, attempt_id, kind, data], ("session_id", "attempt_id", "fingerprint", "kind"),
                (session_id, attempt_id, fingerprint, kind))
            if inserted and kind == "phase_intervals":
                self._accumulate_intervals(session_id, data)
        return identity

    def _accumulate_intervals(self, session_id, data):
        intervals = data.get("intervals")
        if not isinstance(intervals, (list, tuple)):
            raise ValueError("Phase durations require captured monotonic intervals")
        row = self.db.execute("SELECT durations_json,run_id FROM learning_sessions WHERE session_id=?", (session_id,)).fetchone()
        if data.get("run_id", row[1]) != row[1]:
            raise ValueError("Monotonic phase intervals cannot cross application runs")
        durations = json.loads(row[0])
        for interval in intervals:
            _object(interval, "phase interval")
            phase = _identifier(interval.get("phase"), "phase")
            start, end = interval.get("start"), interval.get("end")
            if (isinstance(start, bool) or isinstance(end, bool)
                    or not isinstance(start, (float, int)) or not isinstance(end, (float, int))
                    or start < 0 or end < start):
                raise ValueError("Phase durations require ordered nonnegative monotonic seconds")
            durations[phase] = durations.get(phase, 0.0) + end-start
        self.db.execute("UPDATE learning_sessions SET durations_json=? WHERE session_id=?", (_json(durations), session_id))

    def add_decision(self, decision_id, session_id, attempt_id, data):
        _object(data, "decision data")
        with sqlite_atomic(self.db):
            fingerprint = self._linked_attempt(session_id, attempt_id, data)
            return self._stable_insert("learning_decisions", "decision_id", decision_id,
                [session_id, attempt_id, data], ("session_id", "attempt_id", "fingerprint"),
                (session_id, attempt_id, fingerprint))

    def record_outcome(self, outcome_id, decision_id, attempt_id, data):
        _object(data, "outcome data")
        with sqlite_atomic(self.db):
            row = self.db.execute("SELECT session_id FROM learning_decisions WHERE decision_id=?", (decision_id,)).fetchone()
            if not row:
                raise ValueError("An outcome needs a recorded decision")
            self._session(row[0], require_open=False)
            if attempt_id is not None and self._attempt(attempt_id)[0] != row[0]:
                raise ValueError("A proximal outcome cannot cross practice sessions")
            return self._stable_insert("learning_outcomes", "outcome_id", outcome_id,
                [decision_id, attempt_id, data], ("decision_id", "attempt_id"), (decision_id, attempt_id))

    def _censor_decisions(self, session_id, reason):
        rows = self.db.execute("""SELECT decision_id FROM learning_decisions d WHERE session_id=?
            AND NOT EXISTS (SELECT 1 FROM learning_outcomes o WHERE o.decision_id=d.decision_id)""", (session_id,)).fetchall()
        for (identity,) in rows:
            self.record_outcome(identity + ":proximal", identity, None,
                                {"kind": "proximal", "state": "censored", "reason": reason})
        # A proximal exposure can be observed while the original-target
        # verification is still pending. Close that episode separately.
        episodes = {}
        for decision, encoded in self.db.execute(
                "SELECT decision_id,summary_json FROM learning_decisions WHERE session_id=? ORDER BY rowid",
                (session_id,)):
            episode = json.loads(encoded).get("episode_id")
            if episode:
                episodes.setdefault(episode, decision)
        for episode, decision in episodes.items():
            identity = episode + ":verification"
            if not self.db.execute("SELECT 1 FROM learning_outcomes WHERE outcome_id=?", (identity,)).fetchone():
                self.record_outcome(identity, decision, None,
                    {"kind": "episode_verification", "episode_id": episode,
                     "state": "censored", "reason": reason})

    def close_session(self, session_id, reason):
        _identifier(reason, "session closure reason")
        with sqlite_atomic(self.db):
            self._session(session_id, require_open=False)
            row = self.db.execute("SELECT closure_reason FROM learning_sessions WHERE session_id=?", (session_id,)).fetchone()
            if row[0] is not None:
                if row[0] != reason:
                    raise ValueError("Conflicting session closure replay")
                return
            if self.db.execute("SELECT 1 FROM learning_attempts WHERE session_id=? AND state='open'", (session_id,)).fetchone():
                raise ValueError("Settle the open attempt before closing its practice session")
            self._censor_decisions(session_id, reason)
            self.db.execute("UPDATE learning_sessions SET ended_utc=?,closure_reason=? WHERE session_id=?", (_utc(), reason, session_id))

    def recover_open_sessions(self) -> int:
        # A crash envelope can be slightly larger than its last checkpoint.
        # Close the interrupted sessions before enforcing retention so startup
        # can prune eligible closed detail instead of becoming impossible.
        with sqlite_atomic(self.db):
            self._recovering = True
            try:
                count = self._recover_open_sessions()
            finally:
                self._recovering = False
            self._enforce_budget()
            return count

    def _recover_open_sessions(self) -> int:
        """Startup-only recovery. The unknown crash suffix receives no assessment."""
        with sqlite_atomic(self.db):
            sessions = self.db.execute("SELECT session_id FROM learning_sessions WHERE learner_id=? AND closure_reason IS NULL", (self.learner_id,)).fetchall()
            for (session_id,) in sessions:
                events = self.db.execute("""SELECT kind,summary_json FROM learning_events
                    WHERE session_id=? AND kind IN ('settings_intent','settings_applied')""", (session_id,)).fetchall()
                applied = {json.loads(encoded).get("intent_id") for kind, encoded in events if kind == "settings_applied"}
                for kind, encoded in events:
                    intent = json.loads(encoded).get("intent_id")
                    if kind == "settings_intent" and intent and intent not in applied:
                        self.record_event(session_id, "settings_uncertain", {"intent_id": intent,
                            "applied": None, "reason": "process_interrupted",
                            "missingness": "No durable applied confirmation; the setting may or may not have changed"},
                            event_id=str(uuid5(NAMESPACE_URL, f"piano:settings-uncertain:{session_id}:{intent}")))
                attempts = self.db.execute("SELECT attempt_id,checkpoint_json FROM learning_attempts WHERE session_id=? AND state='open'", (session_id,)).fetchall()
                for attempt_id, encoded in attempts:
                    prefix = json.loads(encoded) if encoded else {}
                    self.settle_attempt(attempt_id, {"state": "process_interrupted", "reason": "process_interrupted",
                        "ended_utc": None, "monotonic_end": None, "assessment": None,
                        "played": prefix.get("played", []),
                        "checkpoint": {k: v for k, v in prefix.items() if k != "played"} or None,
                        "capture_suffix": "unknown", "observations": []})
                self._censor_decisions(session_id, "process_interrupted")
                self.db.execute("UPDATE learning_sessions SET closure_reason='process_interrupted',recovered_utc=? WHERE session_id=?", (_utc(), session_id))
            return len(sessions)

    def migrate_legacy(self):
        """Called inside ProgressRepository's versioned migration savepoint."""
        if not self._table_exists("practice_evidence"):
            return
        rows = self.db.execute("SELECT id,fingerprint,stage_key,bpm,statuses,extra_notes FROM practice_evidence ORDER BY id").fetchall()
        session_id = str(uuid5(NAMESPACE_URL, "piano:legacy-bounded:session"))
        if rows:
            self.db.execute("""INSERT INTO learning_sessions
                (session_id,learner_id,run_id,closure_reason,start_hash) VALUES (?,?,?,'legacy_bounded',?)""",
                (session_id, self.learner_id, "legacy_bounded", _hash(["legacy_bounded", session_id])))
        for old_id, fingerprint, stage_key, bpm, encoded, extra in rows:
            context = {"fingerprint": fingerprint, "stage_key": stage_key, "provenance": "legacy_bounded"}
            assessment = {"statuses": json.loads(encoded), "extra_notes": extra, "bpm": bpm,
                          "clean": None, "passed": None, "mastery_eligible": False,
                          "missingness": {"passed": "unknown", "timing": "unknown", "rules": "unknown", "timestamps": "unknown"}}
            attempt_id = str(uuid5(NAMESPACE_URL, f"piano:legacy-bounded:attempt:{old_id}:{fingerprint}:{stage_key}"))
            self.db.execute("""INSERT INTO learning_attempts
                (attempt_id,session_id,fingerprint,stage_key,state,reason,context_hash,terminal_hash,summary_json,provenance)
                VALUES (?,?,?,?,'legacy_bounded','legacy_bounded',?,?,?,'legacy_bounded')""",
                (attempt_id, session_id, fingerprint, stage_key, _hash(context), _hash(assessment), _json(context)))
            self._insert_assessment(attempt_id, stage_key, assessment, legacy=True)
        if self.db.execute("SELECT count(*) FROM learning_attempts WHERE provenance='legacy_bounded'").fetchone()[0] != len(rows):
            raise ValueError("Legacy evidence migration row verification failed")
        self.db.execute("DROP TABLE practice_evidence")

    def _table_exists(self, table):
        return self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None

    def _enforce_budget(self):
        self.retention.enforce_budget(recovering=self._recovering)

    def prune(self, days=365, budget_mib=256, now_utc=None) -> dict:
        return self.retention.prune(days, budget_mib, now_utc)

    def status(self) -> dict:
        return self.retention.status()

    def export(self, path, *, include_detail=False) -> dict:
        return self.history_exporter.export(path, include_detail=include_detail)

    def _delete_progress(self, fingerprint=None):
        for table in _PROGRESS_TABLES:
            if self._table_exists(table):
                if fingerprint is None:
                    self.db.execute(f"DELETE FROM {table}")
                else:
                    self.db.execute(f"DELETE FROM {table} WHERE fingerprint=?", (fingerprint,))

    def _delete_orphan_rules(self):
        # Rules referenced in events/decisions can outlive their triggering take.
        referenced = {row[0] for row in self.db.execute("SELECT rule_id FROM learning_attempts WHERE rule_id IS NOT NULL")}
        for table in ("learning_events", "learning_decisions", "learning_outcomes"):
            for (encoded,) in self.db.execute(f"SELECT summary_json FROM {table}"):
                rule = json.loads(encoded).get("rule_id")
                if isinstance(rule, str):
                    referenced.add(rule)
        for (rule,) in self.db.execute("SELECT rule_id FROM learning_rules").fetchall():
            if rule not in referenced:
                self.db.execute("DELETE FROM learning_rules WHERE rule_id=?", (rule,))

    def delete_piece(self, fingerprint):
        _identifier(fingerprint, "source fingerprint")
        with sqlite_atomic(self.db):
            self.db.execute("""DELETE FROM learning_events WHERE fingerprint=?
                OR json_extract(summary_json,'$.before.fingerprint')=?
                OR json_extract(summary_json,'$.after.fingerprint')=?
                OR json_extract(summary_json,'$.parameters.fingerprint')=?""",
                (fingerprint, fingerprint, fingerprint, fingerprint))
            self.db.execute("DELETE FROM learning_decisions WHERE fingerprint=?", (fingerprint,))
            self.db.execute("DELETE FROM learning_attempts WHERE fingerprint=?", (fingerprint,))
            self._delete_progress(fingerprint)
            self._delete_orphan_rules()

    def delete_learner(self) -> str:
        with sqlite_atomic(self.db):
            self.db.execute("DELETE FROM learning_learners")
            self._delete_progress()
            self.db.execute("DELETE FROM learning_rules")
            return self._new_learner()
