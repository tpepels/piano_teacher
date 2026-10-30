"""SQLite persistence for the learner's local practice progress.

This repository owns the connection, schema migration, and durable records.
PracticeEngine owns application transitions, MIDI, rendering and the lock.
The LearningPlan is supplied explicitly to avoid a reverse engine dependency.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .learning import LearningPlan, build_exercises
from .exercise_generator import generate_variants
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
        row = self.db.execute("""SELECT exercise,hand,bpm,streak,target_bpm,
                      variant_index,route_version,step_key,first_bar,last_bar,
                      level,exercise_kind FROM strategy_sessions
                      WHERE fingerprint=? AND strategy=?""",
                      (fingerprint, p.exercise_strategy.name)).fetchone()
        if row is None:
            row = self.db.execute("SELECT exercise,hand,bpm,streak,target_bpm,variant_index,route_version,step_key,first_bar,last_bar,level,exercise_kind FROM sessions WHERE fingerprint=?",(fingerprint,)).fetchone()
        # The session row is piece-wide, while mastery/tempo/history keys are
        # strategy-specific. Never restore another strategy's session BPM
        # or clean streak, including after changing the preference offline.
        if row and isinstance(row[7], str) and row[7].startswith("course:"):
            segments = row[7].split(":")
            saved_strategy = (segments[2] if len(segments) > 2
                              and segments[2] not in ("learn", "connect", "perform", "warmup")
                              else "legacy")
            if saved_strategy != p.exercise_strategy.name and not p.warmup:
                # Target tempo belongs to the piece, not the chosen exercise
                # generator. Do not inherit position, BPM or clean streak.
                if row[4] is not None:
                    p.target_bpm = max(SETTINGS.minimum_bpm,
                        min(SETTINGS.maximum_bpm, int(row[4])))
                row = None
        legacy_exercises = None
        if row and restore_session:
            exact = next((step for step in p.lesson_steps if step.key == row[7]), None)
            if exact is not None:
                p.restore_location(kind=exact.kind, first_bar=exact.first_bar, last_bar=exact.last_bar,
                                   hand=exact.hand, level=exact.level)
                equivalent = True
            elif row[6] and row[8] is not None and row[9] is not None:
                p.restore_location(kind=row[11] or "learn", first_bar=int(row[8]), last_bar=int(row[9]),
                                   hand=row[1], level=row[10] or "original")
                equivalent = False
            else:
                # Old integer positions refer to the old two-bar route. Never
                # interpret them as positions in the new consolidated course.
                legacy_exercises = build_exercises(p.piece, consolidate=False, adaptive_focus=False)
                old = legacy_exercises[min(max(0, int(row[0])), len(legacy_exercises) - 1)]
                hand = row[1] if row[1] in ("right", "left", "both") else "both"
                old_variants = generate_variants(old.phrase, hand)
                if not old_variants:
                    hand = "both"
                    old_variants = generate_variants(old.phrase, hand)
                old_variant = old_variants[min(max(0, int(row[5] or 0)), len(old_variants) - 1)]
                p.restore_location(kind=old.kind, first_bar=old.phrase.first_bar, last_bar=old.phrase.last_bar,
                                   hand=hand, level=old_variant.level)
                equivalent = (row[1] == hand and p.hand == hand and p.active_variant.level == old_variant.level
                              and p.active_phrase.start == old_variant.phrase.start
                              and p.active_phrase.end == old_variant.phrase.end
                              and p.active_phrase.notes == old_variant.notes
                              # Old unversioned whole-performance rows did
                              # not record whether the final sustained note
                              # or previously silent measures were included.
                              # Reuse their tempo, but never an unverifiable
                              # target-speed clean streak.
                              and old.kind != "perform")
            p.set_bpm(max(SETTINGS.minimum_bpm, min(SETTINGS.maximum_bpm, int(row[4] or p.piece.bpm))))
            p.bpm = max(SETTINGS.minimum_bpm, min(p.target_bpm, int(row[2])))
            p.streak = min(SETTINGS.clean_runs_to_master-1, max(0, int(row[3]))) if equivalent else 0
        for key,bpm in self.db.execute("SELECT stage_key,bpm FROM stage_tempos WHERE fingerprint=?",(fingerprint,)):
            if any(step.key == key for step in p.lesson_steps):
                p.stage_tempos[key] = max(SETTINGS.minimum_bpm,
                                          min(p.target_bpm,int(bpm)))
        for (key,) in self.db.execute(
                "SELECT stage_key FROM repeat_tempo_credit WHERE fingerprint=?",
                (fingerprint,)):
            if key in p.stage_tempos:
                p.transferable_tempos.add(key)
        # A current session may predate per-stage tempos; retain its exact
        # judged tempo, but only when the stage can be identified reliably.
        if row is not None and restore_session:
            p.stage_tempos[p.identity] = p.bpm
        for key,bpm in self.db.execute("SELECT exercise,bpm FROM mastery WHERE fingerprint=?",(fingerprint,)):
            p.mastered[key]=bpm
        # Preserve legacy rows, and recognize them only when the exact same
        # hand, level and source events still form an individual course stage.
        legacy_mastery = [(key, bpm) for key, bpm in p.mastered.items() if not key.startswith("course:")]
        if legacy_mastery and restore_session and p.exercise_strategy.name == 'legacy':
            legacy_exercises = legacy_exercises or build_exercises(p.piece, consolidate=False)
            for old in legacy_exercises:
                for hand in ("right", "left", "both"):
                    for variant in generate_variants(old.phrase, hand):
                        legacy_key = f"{old.key}:{hand}:{variant.level}"
                        if legacy_key not in p.mastered:
                            continue
                        new_key = p._stage_key(old, hand, variant)
                        if any(step.key == new_key for step in p.lesson_steps):
                            p.mastered[new_key] = p.mastered[legacy_key]


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
            (fingerprint,p.exercise_strategy.name,p.index,p.hand,p.bpm,p.streak,p.target_bpm,
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
