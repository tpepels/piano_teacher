"""One local, transactional ledger of exposure, grading and intervention facts.

The application owns IDs, musical timing and the connection. This module never
grades, rematches MIDI, infers a legacy pass, or independently commits a take.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from collections import Counter
from hashlib import sha256
import json
import math
from pathlib import Path
import sqlite3
from uuid import NAMESPACE_URL, uuid4, uuid5

from .diagnosis_policies import AssessmentEvidence, LearnerSnapshot
from .sqlite_transaction import sqlite_atomic


SCHEMA_VERSION = 1
_PROGRESS_TABLES = ("strategy_sessions", "learner_units", "learner_stages",
                    "repeat_tempo_credit", "stage_tempos", "mastery", "sessions",
                    "fukuda_mistakes")


class LearningLedgerLimitError(ValueError):
    """Detail cannot fit without discarding an open or pending exposure."""


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _identifier(value, label="identity") -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"A nonempty {label} is required")
    return value


def _validate(value):
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Evidence numbers must be finite")
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _validate(item)
        return
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for item in value.values():
            _validate(item)
        return
    raise ValueError("Evidence must be finite JSON with string object keys")


def _json(value) -> str:
    _validate(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=False)


def _hash(value) -> str:
    return sha256(_json(value).encode("utf-8")).hexdigest()


def _object(value, label="payload") -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"The {label} must be a JSON object")
    _validate(value)
    return value


def _compact(value):
    """Small facts retained after detail pruning; omission is labeled in coverage."""
    if isinstance(value, dict):
        return {key: _compact(item) for key, item in value.items()
                if not isinstance(item, str) or len(item) <= 1024}
    if isinstance(value, (list, tuple)):
        if len(value) <= 16 and all(not isinstance(item, (dict, list, tuple)) for item in value):
            return list(value)
        return {"item_count": len(value), "detail_required": True}
    return value


_CONTEXT_FACTS = frozenset((
    "score_revision", "from_beat", "phrase_start", "phrase_end", "assistance",
    "calibration_ms", "calibration_applied_ms", "midi_available", "count_in_beats", "count_in_meter", "scheduled_origin",
    "fingerprint", "stage_key", "rule_id", "generator", "generator_version", "strategy",
    "strategy_version", "hand", "variant", "level", "classification", "mode", "scope",
    "target_bpm", "source_bpm", "performed_bpm", "bpm", "tempo_map_hash", "transport_id", "revision",
    "started_utc", "monotonic_start", "run_id", "parent_decision_id", "first_bar", "last_bar",
    "start_beat", "end_beat", "full_target", "mastery_eligible", "eligibility_reason",
    "calibration", "calibration_ms", "device_available", "midi_available", "assistance",
    "score_revision", "phrase_start", "phrase_end", "from_beat", "source_sha256", "provenance"))


def _context_summary(value: dict) -> dict:
    return _compact({key: item for key, item in value.items() if key in _CONTEXT_FACTS})


def _redact(value):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            normalized = key.lower().replace("-", "_")
            if ("path" in normalized or normalized in {"name", "title", "filename", "file_name", "raw_midi", "midi_bytes",
                    "music_dir", "midi_device", "last_piece", "source", "device"}
                    or normalized.endswith("_name") or normalized.endswith("_title")
                    or normalized in {"device", "piece"} and isinstance(item, str)):
                continue
            result[key] = _redact(item)
            if normalized.endswith("_residual") and isinstance(item, (int, float)) and not isinstance(item, bool):
                result[key + "_microseconds"] = round(item * 1_000_000)
            if normalized.endswith("_residual_seconds") and isinstance(item, (int, float)) and not isinstance(item, bool):
                result[key[:-7] + "microseconds"] = round(item * 1_000_000)
        return result
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


class LearningLedger:
    """Connection-scoped evidence owner; all mutations compose with sqlite_atomic."""

    def __init__(self, db: sqlite3.Connection):
        self.db = db
        self._recovering = False
        # ProgressRepository enables this before beginning migration. Standalone
        # use on a fresh connection gets the same relational protections.
        self.db.execute("PRAGMA foreign_keys=ON")
        with sqlite_atomic(db):
            self._create_schema()
            if not db.execute("SELECT 1 FROM learning_current_learner").fetchone():
                self._new_learner()

    def _create_schema(self):
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
            self.db.execute(statement)
        self.db.execute("INSERT OR IGNORE INTO learning_retention VALUES (1,365,256)")
        self.db.execute("""CREATE TABLE IF NOT EXISTS learning_detail_usage (
            singleton INTEGER PRIMARY KEY CHECK(singleton=1), logical_bytes INTEGER NOT NULL CHECK(logical_bytes>=0))""")
        if not self.db.execute("SELECT 1 FROM learning_detail_usage WHERE singleton=1").fetchone():
            self.db.execute("INSERT INTO learning_detail_usage VALUES (1,?)", (self._scan_detail_bytes(),))
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
                self.db.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_usage_{suffix}
                    AFTER {event} ON {table} BEGIN
                    UPDATE learning_detail_usage SET logical_bytes=logical_bytes{change} WHERE singleton=1;
                    END""")

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
        AssessmentEvidence(stage_key, tuple(statuses), extra, bpm)
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

    def recent(self, fingerprint, stage_key, limit=8) -> LearnerSnapshot:
        _identifier(fingerprint, "source fingerprint")
        _identifier(stage_key, "exact stage key")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 64:
            raise ValueError("History needs a bounded query from 1 to 64")
        rows = self.db.execute("""SELECT a.bpm,a.statuses_json,a.extra_notes
            FROM learning_assessments a JOIN learning_attempts t USING(attempt_id)
            JOIN learning_sessions s USING(session_id)
            WHERE s.learner_id=? AND t.fingerprint=? AND t.stage_key=? AND a.assessed=1
            AND a.statuses_json<>'[]'
            AND (t.provenance='legacy_bounded' OR
                 (t.state='completed' AND json_extract(t.summary_json,'$.scope')='full'))
            ORDER BY a.id DESC LIMIT ?""", (self.learner_id, fingerprint, stage_key, limit)).fetchall()
        return LearnerSnapshot(stage_key, tuple(AssessmentEvidence(stage_key, tuple(json.loads(statuses)), extra, bpm)
                                                for bpm, statuses, extra in reversed(rows)))

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

    def _scan_detail_bytes(self) -> int:
        expressions = (
            "SELECT coalesce(sum(coalesce(length(CAST(context_json AS BLOB)),0)+coalesce(length(CAST(checkpoint_json AS BLOB)),0)),0) FROM learning_attempts",
            "SELECT coalesce(sum(length(CAST(detail_json AS BLOB))),0) FROM learning_attempt_details",
            *(f"SELECT coalesce(sum(length(CAST(data_json AS BLOB))),0) FROM {table}" for table in ("learning_events", "learning_decisions", "learning_outcomes")),
        )
        return sum(self.db.execute(query).fetchone()[0] for query in expressions)

    def _logical_detail_bytes(self) -> int:
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
            if (completed_utc is not None and completed_utc < cutoff) or self._logical_detail_bytes() > budget_mib * 1024 * 1024:
                pruned += self._prune_session(session_id)
        if self._logical_detail_bytes() > budget_mib * 1024 * 1024:
            raise LearningLedgerLimitError("The logical detail budget limit cannot fit open or pending evidence")
        return pruned

    def _enforce_budget(self):
        if self._recovering:
            return
        days, budget = self.db.execute("SELECT days,budget_mib FROM learning_retention WHERE singleton=1").fetchone()
        if self._logical_detail_bytes() > budget * 1024 * 1024:
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
                "logical_detail_bytes": self._logical_detail_bytes(), "detail_days": days,
                "detail_budget_mib": budget, "coverage": coverage}

    def _rows(self, table):
        cursor = self.db.execute(f"SELECT * FROM {table}")
        names = [column[0] for column in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]

    def export(self, path, *, include_detail=False) -> dict:
        if not isinstance(include_detail, bool):
            raise ValueError("Detailed export must be explicitly selected")
        with sqlite_atomic(self.db):
            attempts = self._rows("learning_attempts")
            for row in attempts:
                row["summary"] = json.loads(row.pop("summary_json"))
                context = row.pop("context_json")
                checkpoint = row.pop("checkpoint_json")
                row["context"] = json.loads(context) if include_detail and context else row["summary"]
                row["checkpoint"] = json.loads(checkpoint) if include_detail and checkpoint else None
                detail = self.db.execute("SELECT detail_json FROM learning_attempt_details WHERE attempt_id=?", (row["attempt_id"],)).fetchone()
                row["detail"] = json.loads(detail[0]) if include_detail and detail else None
                row["detail_pruned"] = bool(row["detail_pruned"])
            assessments = self._rows("learning_assessments")
            for row in assessments:
                row["summary"] = json.loads(row.pop("summary_json"))
                row["statuses"] = json.loads(row.pop("statuses_json"))
                for key in ("clean", "passed", "mastery_eligible", "assessed"):
                    if row[key] is not None:
                        row[key] = bool(row[key])
            result = {"schema_version": SCHEMA_VERSION, "exported_utc": _utc(), "learner_id": self.learner_id,
                      "include_detail": include_detail, "units": {"beats": "quarter_notes", "times": "seconds",
                          "residuals": "seconds", "derived_residuals": "integer_microseconds", "tempo": "beats_per_minute",
                          "monotonic": "seconds_within_run_only", "calendar": "UTC"},
                      "missingness": {"unknown": "null or an explicit unknown marker; never a measured zero",
                          "legacy_bounded": "Only the retained old status window was imported; timing, rules, timestamps and passed are unknown",
                          "pruned_detail": "Compact summaries remain; missing note detail is not a complete lifetime observation",
                          "unavailable": ["physical_hand", "pedal_accuracy", "velocity_accuracy"]},
                      "coverage": self.status()["coverage"], "sessions": self._rows("learning_sessions"),
                      "attempts": attempts, "assessments": assessments,
                      "rules": [{"rule_id": row["rule_id"], "snapshot": json.loads(row["snapshot_json"])}
                                for row in self._rows("learning_rules")]}
            for session in result["sessions"]:
                session["durations_seconds"] = json.loads(session.pop("durations_json"))
            for name in ("events", "decisions", "outcomes"):
                rows = self._rows("learning_" + name)
                for row in rows:
                    row["summary"] = json.loads(row.pop("summary_json"))
                    encoded = row.pop("data_json")
                    row["data"] = json.loads(encoded) if include_detail and encoded else row["summary"]
                result[name] = rows
            result = _redact(result)
        target = Path(path)
        # A failed serialization or write never leaves an apparently complete
        # export at the selected destination.
        encoded = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + "." + str(uuid4()) + ".tmp")
        try:
            temporary.write_text(encoded, encoding="utf-8")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        return {"path": str(target), "schema_version": SCHEMA_VERSION, "attempts": len(attempts), "include_detail": include_detail}

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
