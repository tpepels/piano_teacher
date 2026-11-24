"""SQLite persistence for the learner's local practice progress.

This repository owns the connection, schema migration, and durable records.
PracticeEngine owns application transitions, MIDI, rendering and the lock.
The LearningPlan is supplied explicitly to avoid a reverse engine dependency.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .learning import LearningPlan
from .sqlite_transaction import sqlite_atomic
from .lesson_settings import SETTINGS
from .learner_state import LearnerStateStore
from .learning_ledger import LearningLedger, SCHEMA_VERSION


class ProgressRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path).resolve()
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        # Bounded read-only analytical snapshots must not block the musical
        # worker's evidence/progress commit. WAL keeps the single canonical
        # writer and its existing savepoints while allowing concurrent readers.
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("CREATE TABLE IF NOT EXISTS sessions (fingerprint TEXT PRIMARY KEY, exercise INTEGER, hand TEXT, bpm INTEGER, streak INTEGER, target_bpm INTEGER)")
        columns={row[1] for row in self.db.execute("PRAGMA table_info(sessions)")}
        if "target_bpm" not in columns:
            self.db.execute("ALTER TABLE sessions ADD COLUMN target_bpm INTEGER")
        if "variant_index" not in columns:
            self.db.execute("ALTER TABLE sessions ADD COLUMN variant_index INTEGER NOT NULL DEFAULT 0")
        for column, declaration in (("route_version", "INTEGER"), ("step_key", "TEXT"),
                                    ("first_bar", "INTEGER"), ("last_bar", "INTEGER"),
                                    ("level", "TEXT"), ("exercise_kind", "TEXT")):
            if column not in columns:
                self.db.execute(f"ALTER TABLE sessions ADD COLUMN {column} {declaration}")
        self.db.execute("""CREATE TABLE IF NOT EXISTS strategy_sessions (
            fingerprint TEXT NOT NULL, strategy TEXT NOT NULL,
            exercise INTEGER, hand TEXT, bpm INTEGER, streak INTEGER,
            target_bpm INTEGER, variant_index INTEGER, route_version INTEGER,
            step_key TEXT, first_bar INTEGER, last_bar INTEGER, level TEXT,
            exercise_kind TEXT,
            PRIMARY KEY (fingerprint, strategy))""")
        self.db.execute("CREATE TABLE IF NOT EXISTS mastery (fingerprint TEXT, exercise TEXT, bpm INTEGER, PRIMARY KEY (fingerprint, exercise))")
        self.db.execute("""CREATE TABLE IF NOT EXISTS stage_tempos (
            fingerprint TEXT NOT NULL, stage_key TEXT NOT NULL,
            bpm INTEGER NOT NULL,
            PRIMARY KEY (fingerprint,stage_key))""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS repeat_tempo_credit (
            fingerprint TEXT NOT NULL, stage_key TEXT NOT NULL,
            PRIMARY KEY (fingerprint,stage_key))""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS flow_returns (
            fingerprint TEXT NOT NULL, stage_key TEXT NOT NULL,
            count INTEGER NOT NULL,
            PRIMARY KEY (fingerprint,stage_key))""")
        self.db.commit()
        # One owner initializes both progress and learner-state tables.
        self.learner_store = LearnerStateStore(self.db)
        try:
            with sqlite_atomic(self.db):
                version = self.db.execute("PRAGMA user_version").fetchone()[0]
                if version > SCHEMA_VERSION:
                    raise ValueError("The learning database schema is newer than this application")
                self.ledger = LearningLedger(self.db)
                if version < 1:
                    self.ledger.migrate_legacy()
                    self.db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        except BaseException:
            self.db.close()
            raise

    def restore(self, plan: LearningPlan | None, fingerprint: str, *,
                restore_session: bool = True) -> bool:
        """Saved position, mastery and Free returns for this piece's steps.

        Only keys of the current course count; unknown (older-version) rows
        stay on disk but never award credit. A saved position whose key no
        longer exists falls back to the single-measure window of its first bar.
        """
        p = plan
        if p is None:
            return False
        current = {step.key for step in p.lesson_steps}
        p.mastered = {key: int(bpm) for key, bpm in self.db.execute(
            "SELECT exercise, bpm FROM mastery WHERE fingerprint=?", (fingerprint,))
            if key in current and int(bpm) >= p.piece.bpm}
        p.free_returns = {key: int(count) for key, count in self.db.execute(
            "SELECT stage_key,count FROM flow_returns WHERE fingerprint=?", (fingerprint,))
            if key in current}
        row = self.db.execute(
            """SELECT step_key, first_bar, hand, bpm, streak FROM strategy_sessions
               WHERE fingerprint=? AND strategy=?""",
            (fingerprint, p.profile)).fetchone()
        exact = False
        if row and restore_session:
            exact = p.restore_position(row[0] if isinstance(row[0], str) else None,
                first_bar=int(row[1]) if row[1] is not None else None,
                hand=row[2] if row[2] in ("right", "left", "both") else None)
        p.bpm, p.streak, p.failures = p.target_bpm, 0, 0
        if exact:
            # A restored streak can never already satisfy mastery.
            p.bpm = max(1, min(SETTINGS.maximum_bpm, int(row[3])))
            p.streak = min(p.course_state().clean_runs_required-1, max(0, int(row[4])))
        return bool(row and restore_session)

    def save(self, plan: LearningPlan | None, fingerprint: str) -> None:
        p = plan
        if p is None:
            return
        with sqlite_atomic(self.db):
            row = (p.index, p.hand, p.bpm, p.streak, p.target_bpm, p.variant_index,
                   p.route_version, p.identity, p.exercise.phrase.first_bar,
                   p.exercise.phrase.last_bar, p.active_variant.level, p.exercise.kind)
            self.db.execute("""INSERT OR REPLACE INTO sessions (fingerprint,exercise,hand,bpm,
                streak,target_bpm,variant_index,route_version,step_key,first_bar,last_bar,
                level,exercise_kind) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", (fingerprint, *row))
            self.db.execute("""INSERT OR REPLACE INTO strategy_sessions
                (fingerprint,strategy,exercise,hand,bpm,streak,target_bpm,
                 variant_index,route_version,step_key,first_bar,last_bar,level,exercise_kind)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (fingerprint, p.profile, *row))
            for key, bpm in p.mastered.items():
                self.db.execute("INSERT OR REPLACE INTO mastery VALUES (?,?,?)", (fingerprint,key,bpm))
            for key, count in p.free_returns.items():
                self.db.execute("INSERT OR REPLACE INTO flow_returns VALUES (?,?,?)",
                                (fingerprint,key,count))

    def reset_piece(self, fingerprint: str) -> None:
        """Reset saved progress while preserving the authoritative evidence ledger."""
        with sqlite_atomic(self.db):
            for table in ("strategy_sessions", "learner_units", "learner_stages", "repeat_tempo_credit",
                          "stage_tempos", "mastery", "sessions", "flow_returns"):
                self.db.execute(f"DELETE FROM {table} WHERE fingerprint=?", (fingerprint,))
            # A reset is historical exposure context, distinct from deletion.
            session = self.db.execute("""SELECT session_id FROM learning_sessions
                WHERE learner_id=? AND closure_reason IS NULL ORDER BY rowid DESC LIMIT 1""",
                (self.ledger.learner_id,)).fetchone()
            if session:
                self.ledger.record_event(session[0], "progress_reset", {"fingerprint": fingerprint})

    def close(self) -> None:
        self.db.close()
