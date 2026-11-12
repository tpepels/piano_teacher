"""Read-only per-stage recommendations from the authoritative learning ledger.

No history record can grant source mastery, alter timing, or overwrite existing
course progress. The key includes the selected strategy and exact note content.
"""
from __future__ import annotations

from .diagnosis_policies import (

    AssessmentEvidence, LearnerSnapshot, PracticeRecommendation,
    resolve_diagnosis_strategy, resolve_learner_strategy,
)


class PracticePolicyService:
    """Composed diagnostic and learner-state strategies, initially advisory."""
    def __init__(self, store, diagnosis=None, learner=None):
        self.store = store
        self.diagnosis = resolve_diagnosis_strategy(diagnosis or "error-family")
        self.learner = resolve_learner_strategy(learner or "repeated-error")

    def observe(self, fingerprint: str, evidence: AssessmentEvidence) -> PracticeRecommendation:
        history = self.store.recent(fingerprint, evidence.stage_key)
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
