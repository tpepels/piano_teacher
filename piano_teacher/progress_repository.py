"""SQLite persistence for the learner's local practice progress.

This repository owns the connection, schema migration, and durable records.
PracticeEngine owns application transitions, MIDI, rendering and the lock.
The LearningPlan is supplied explicitly to avoid a reverse engine dependency.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .learning import LearningPlan
from .lesson_settings import SETTINGS
from .learner_state import LearnerStateStore
from .practice_history import AssessmentHistoryStore


class ProgressRepository:
    def __init__(self, db_path: Path) -> None:
        self.db = sqlite3.connect(db_path, check_same_thread=False)
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
        self.db.commit()
        # One owner initializes both progress and learner-state tables.
        self.learner_store = LearnerStateStore(self.db)
        self.assessment_history = AssessmentHistoryStore(self.db)

    def restore(self, plan: LearningPlan | None, fingerprint: str, *,
                restore_session: bool = True) -> None:
        p = plan
        if p is None:
            return
        # The piece-wide target is independent of the selected curriculum.
        # The sessions table is the current per-piece target owner. Its old
        # positional fields are never interpreted as lesson indices.
        saved_target = self.db.execute(
            "SELECT target_bpm FROM sessions WHERE fingerprint=?", (fingerprint,)
        ).fetchone()
        if saved_target and saved_target[0] is not None:
            p.target_bpm = max(SETTINGS.minimum_bpm, min(
                SETTINGS.maximum_bpm, int(saved_target[0])))

        # One source of session position: an explicitly saved strategy with a
        # versioned, content-derived stage identity. Unknown historical course
        # rows are retained on disk but never executed or awarded credit.
        row = self.db.execute(
            """SELECT step_key, first_bar, last_bar, hand, level, exercise_kind,
                      bpm, streak FROM strategy_sessions
               WHERE fingerprint=? AND strategy=?""",
            (fingerprint, p.profile),
        ).fetchone()
        current = {step.key: step for step in p.lesson_steps}
        exact = False
        if row and restore_session and isinstance(row[0], str):
            selected = current.get(row[0])
            if selected is not None:
                p.restore_location(
                    kind=selected.kind, first_bar=selected.first_bar,
                    last_bar=selected.last_bar, hand=selected.hand,
                    level=selected.level)
                exact = p.identity == selected.key
            elif row[1] is not None and row[2] is not None:
                # After a generator version change, retain a navigable
                # source-measure location, never old proficiency or tempo.
                p.restore_location(
                    kind=row[5] or "learn",
                    first_bar=int(row[1]), last_bar=int(row[2]),
                    hand=row[3] if row[3] in ("right", "left", "both") else "both",
                    level=row[4] or "")

        p.stage_tempos.clear()
        p.transferable_tempos.clear()
        p.mastered.clear()
        for key, bpm in self.db.execute(
            "SELECT stage_key, bpm FROM stage_tempos WHERE fingerprint=?",
            (fingerprint,),
        ):
            if key in current:
                p.stage_tempos[key] = max(SETTINGS.minimum_bpm, min(
                    p.target_bpm, int(bpm)))
        for (key,) in self.db.execute(
            "SELECT stage_key FROM repeat_tempo_credit WHERE fingerprint=?",
            (fingerprint,),
        ):
            if key in p.stage_tempos:
                p.transferable_tempos.add(key)
        for key, bpm in self.db.execute(
            "SELECT exercise, bpm FROM mastery WHERE fingerprint=?",
            (fingerprint,),
        ):
            if key in current:
                p.mastered[key] = bpm

        if exact:
            # A matching, current-version source stage may safely restore its
            # deliberate BPM and clean-pass streak; no other row may.
            p.bpm = max(SETTINGS.minimum_bpm, min(
                p.target_bpm, int(row[6])))
            p.streak = min(SETTINGS.clean_runs_to_master - 1,
                           max(0, int(row[7])))
            p.stage_tempos[p.identity] = p.bpm
        else:
            p.bpm = p._tempo_for_current_stage()
            p.streak = 0

    def has_strategy_session(self, fingerprint: str, strategy: str) -> bool:
        return self.db.execute(
            "SELECT 1 FROM strategy_sessions WHERE fingerprint=? AND strategy=?",
            (fingerprint, strategy)).fetchone() is not None

    def save(self, plan: LearningPlan | None, fingerprint: str) -> None:
        p=plan
        if p is None:
            return
        prior = self.db.execute("SELECT target_bpm FROM sessions WHERE fingerprint=?",
                                (fingerprint,)).fetchone()
        if prior and prior[0] is not None and int(prior[0]) != p.target_bpm:
            # A new piece-wide target must not resurrect the former BPM
            # ladders on later navigation or after restarting the app.
            self.db.execute("DELETE FROM stage_tempos WHERE fingerprint=?",
                            (fingerprint,))
            self.db.execute("DELETE FROM repeat_tempo_credit WHERE fingerprint=?",
                            (fingerprint,))
            # Old per-strategy BPM/streak targets cannot be revived after
            # changing the piece-wide target tempo.
            self.db.execute("DELETE FROM strategy_sessions WHERE fingerprint=?",
                            (fingerprint,))
        self.db.execute("INSERT OR REPLACE INTO sessions (fingerprint,exercise,hand,bpm,streak,target_bpm,variant_index,route_version,step_key,first_bar,last_bar,level,exercise_kind) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (fingerprint,p.index,p.hand,p.bpm,p.streak,p.target_bpm,p.variant_index,
                         p.route_version,p.identity,p.exercise.phrase.first_bar,p.exercise.phrase.last_bar,
                         p.active_variant.level,p.exercise.kind))
        self.db.execute("""INSERT OR REPLACE INTO strategy_sessions
            (fingerprint,strategy,exercise,hand,bpm,streak,target_bpm,
             variant_index,route_version,step_key,first_bar,last_bar,level,exercise_kind)
             VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (fingerprint,p.profile,p.index,p.hand,p.bpm,p.streak,p.target_bpm,
             p.variant_index,p.route_version,p.identity,p.exercise.phrase.first_bar,
             p.exercise.phrase.last_bar,p.active_variant.level,p.exercise.kind))
        p.stage_tempos[p.identity] = p.bpm
        for key, bpm in p.stage_tempos.items():
            self.db.execute("INSERT OR REPLACE INTO stage_tempos VALUES (?,?,?)",
                            (fingerprint,key,bpm))
        for key in p.transferable_tempos:
            self.db.execute("INSERT OR REPLACE INTO repeat_tempo_credit VALUES (?,?)",
                            (fingerprint,key))
        for key, bpm in p.mastered.items():
            self.db.execute("INSERT OR REPLACE INTO mastery VALUES (?,?,?)", (fingerprint,key,bpm))
        self.db.commit()


    def reset_piece(self, fingerprint: str) -> None:
        """Delete one piece's saved path and learner records transactionally."""
        with self.db:
            for table in ("practice_evidence", "strategy_sessions", "learner_units", "learner_stages", "repeat_tempo_credit",
                          "stage_tempos", "mastery", "sessions"):
                self.db.execute(f"DELETE FROM {table} WHERE fingerprint=?", (fingerprint,))

    def close(self) -> None:
        self.db.close()
