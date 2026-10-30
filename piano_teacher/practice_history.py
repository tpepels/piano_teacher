"""Durable, bounded, per-stage evidence for experimental practice policies.

No history record can grant source mastery, alter timing, or overwrite existing
course progress. The key includes the selected strategy and exact note content.
"""
from __future__ import annotations

import json
import sqlite3

from .exercise_contracts import (
    AssessmentEvidence, LearnerSnapshot, PracticeRecommendation,
    resolve_diagnosis_strategy, resolve_learner_strategy,
)


class AssessmentHistoryStore:
    def __init__(self, db: sqlite3.Connection):
        self.db = db
        with db:
            db.execute("""CREATE TABLE IF NOT EXISTS practice_evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fingerprint TEXT NOT NULL, stage_key TEXT NOT NULL,
                bpm REAL NOT NULL, statuses TEXT NOT NULL, extra_notes INTEGER NOT NULL)""")
            db.execute("""CREATE INDEX IF NOT EXISTS idx_practice_evidence_stage
                       ON practice_evidence(fingerprint, stage_key, id)""")

    def recent(self, fingerprint: str, stage_key: str, limit: int = 8) -> LearnerSnapshot:
        if not fingerprint or not stage_key or not 1 <= limit <= 64:
            raise ValueError("History needs a piece, stage, and bounded query")
        rows = self.db.execute(
            """SELECT bpm,statuses,extra_notes FROM practice_evidence
               WHERE fingerprint=? AND stage_key=? ORDER BY id DESC LIMIT ?""",
            (fingerprint, stage_key, limit)).fetchall()
        return LearnerSnapshot(stage_key, tuple(
            AssessmentEvidence(stage_key, tuple(json.loads(statuses)), int(extra), float(bpm))
            for bpm, statuses, extra in reversed(rows)))

    def record(self, fingerprint: str, evidence: AssessmentEvidence) -> LearnerSnapshot:
        if not fingerprint or not evidence.assessed or not evidence.statuses:
            raise ValueError("Only actual scored takes may enter learner history")
        with self.db:
            self.db.execute(
                """INSERT INTO practice_evidence(fingerprint,stage_key,bpm,statuses,extra_notes)
                   VALUES (?,?,?,?,?)""",
                (fingerprint, evidence.stage_key, evidence.bpm,
                 json.dumps(evidence.statuses, separators=(",", ":")), evidence.extra_notes))
            # Bound storage per stage, preserving the most recent 64 attempts.
            self.db.execute(
                """DELETE FROM practice_evidence WHERE fingerprint=? AND stage_key=?
                   AND id NOT IN (SELECT id FROM practice_evidence WHERE fingerprint=? AND stage_key=?
                                  ORDER BY id DESC LIMIT 64)""",
                (fingerprint, evidence.stage_key, fingerprint, evidence.stage_key))
        return self.recent(fingerprint, evidence.stage_key)


class PracticePolicyService:
    """Composed diagnostic and learner-state strategies, initially advisory."""
    def __init__(self, store: AssessmentHistoryStore, diagnosis=None, learner=None):
        self.store = store
        self.diagnosis = resolve_diagnosis_strategy(diagnosis or "error-family")
        self.learner = resolve_learner_strategy(learner or "repeated-error")

    def observe(self, fingerprint: str, evidence: AssessmentEvidence) -> PracticeRecommendation:
        history = self.store.record(fingerprint, evidence)
        return self.learner.recommend(history, self.diagnosis)

    def inspect(self, fingerprint: str, stage_key: str) -> dict:
        snapshot = self.store.recent(fingerprint, stage_key)
        recommendation = self.learner.recommend(snapshot, self.diagnosis)
        return {
            "diagnosis_strategy": self.diagnosis.name,
            "learner_strategy": self.learner.name,
            "attempt_count_window": len(snapshot.recent),
            "latest_diagnosis": self.diagnosis.diagnose(snapshot.recent[-1]) if snapshot.recent else "unassessed",
            "recommendation": {
                "focus": recommendation.focus, "action": recommendation.action,
                "basis": recommendation.basis,
            },
        }
