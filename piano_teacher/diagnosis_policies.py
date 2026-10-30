"""Assessment diagnosis and bounded learner-state recommendation strategies.

No transport, engraving or practice-state mutation belongs to these policies.
This module is also the registry for independently selectable advisory policies.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import isfinite
from typing import Protocol

from .practice import Assessment


@dataclass(frozen=True)
class AssessmentEvidence:
    """Immutable diagnostic summary; avoid treating an ungraded preview as data."""
    stage_key: str
    statuses: tuple[str, ...]
    extra_notes: int
    bpm: float
    assessed: bool = True

    @classmethod
    def from_result(cls, stage_key: str, result: Assessment, bpm: float):
        return cls(stage_key, tuple(entry.status for entry in result.notes),
                   result.extra_notes, bpm)

    def __post_init__(self):
        allowed = {"correct", "early", "late", "short", "long", "missed", "wrong"}
        if (not self.stage_key or any(s not in allowed for s in self.statuses)
                or self.extra_notes < 0 or not isfinite(self.bpm) or self.bpm <= 0):
            raise ValueError("Invalid graded assessment evidence")

    @property
    def clean(self) -> bool:
        return self.assessed and bool(self.statuses) and all(
            status == "correct" for status in self.statuses) and not self.extra_notes


@dataclass(frozen=True)
class LearnerSnapshot:
    stage_key: str
    recent: tuple[AssessmentEvidence, ...]

    def __post_init__(self):
        if any(not e.assessed or e.stage_key != self.stage_key for e in self.recent):
            raise ValueError("History must be graded and scoped to one exact stage")


@dataclass(frozen=True)
class PracticeRecommendation:
    focus: str  # pitch, rhythm, duration, accuracy, or none
    action: str  # note-isolation, timing-practice, sustain-practice, repeat, advance
    basis: str


class AssessmentDiagnosisStrategy(Protocol):
    name: str
    def diagnose(self, evidence: AssessmentEvidence) -> str: ...


@dataclass(frozen=True)
class ErrorFamilyDiagnosis:
    """Piano Tutor-inspired error categories, not an inferred root cause."""
    name: str = "error-family"

    def diagnose(self, evidence: AssessmentEvidence) -> str:
        if not evidence.assessed or not evidence.statuses:
            return "unassessed"
        counts = Counter(evidence.statuses)
        families = {
            "pitch": counts["wrong"] + counts["missed"] + evidence.extra_notes,
            "rhythm": counts["early"] + counts["late"],
            "duration": counts["short"] + counts["long"],
        }
        peak = max(families.values())
        if peak == 0:
            return "accuracy"
        tied = [kind for kind, value in families.items() if value == peak]
        return tied[0] if len(tied) == 1 else "mixed"


class LearnerStateStrategy(Protocol):
    name: str
    def recommend(self, snapshot: LearnerSnapshot,
                  diagnosis: AssessmentDiagnosisStrategy) -> PracticeRecommendation: ...


@dataclass(frozen=True)
class RepeatedErrorPolicy:
    """Advisory-only rule: never change BPM or grant mastery without consent."""
    name: str = "repeated-error"

    def recommend(self, snapshot: LearnerSnapshot,
                  diagnosis: AssessmentDiagnosisStrategy) -> PracticeRecommendation:
        if not snapshot.recent:
            return PracticeRecommendation("none", "repeat", "no assessed history")
        latest = snapshot.recent[-1]
        if latest.clean:
            return PracticeRecommendation("none", "advance", "clean assessed take")
        if len(snapshot.recent) < 2:
            return PracticeRecommendation("accuracy", "repeat", "first assessed difficulty")
        prior, current = snapshot.recent[-2:]
        a, b = diagnosis.diagnose(prior), diagnosis.diagnose(current)
        if a != b or b in ("mixed", "unassessed", "accuracy"):
            return PracticeRecommendation("accuracy", "repeat", "inconsistent error families")
        actions = {"pitch": "note-isolation", "rhythm": "timing-practice",
                   "duration": "sustain-practice"}
        return PracticeRecommendation(b, actions[b], "same dominant error family in two consecutive takes")


@dataclass(frozen=True)
class AccuracyOnlyDiagnosis:
    """Uninformed baseline for controlled error-diagnosis comparison."""
    name: str = "accuracy-only"

    def diagnose(self, evidence: AssessmentEvidence) -> str:
        if not evidence.assessed or not evidence.statuses:
            return "unassessed"
        return "accuracy"


@dataclass(frozen=True)
class RepeatOnlyPolicy:
    """Baseline policy without error-triggered intervention."""
    name: str = "repeat-only"

    def recommend(self, snapshot: LearnerSnapshot,
                  diagnosis: AssessmentDiagnosisStrategy) -> PracticeRecommendation:
        if snapshot.recent and snapshot.recent[-1].clean:
            return PracticeRecommendation("none", "advance", "clean assessed take")
        return PracticeRecommendation("accuracy", "repeat", "baseline practice policy")


_DIAGNOSIS_STRATEGIES = {
    "error-family": ErrorFamilyDiagnosis,
    "accuracy-only": AccuracyOnlyDiagnosis,
}
_LEARNER_STRATEGIES = {
    "repeated-error": RepeatedErrorPolicy,
    "repeat-only": RepeatOnlyPolicy,
}



def _resolve_strategy(spec, options: dict, method: str):
    if isinstance(spec, str):
        try:
            return options[spec]()
        except KeyError as error:
            raise ValueError(f"Unknown strategy {spec!r}; choose from {tuple(options)}") from error
    if not isinstance(getattr(spec, "name", None), str) or not callable(getattr(spec, method, None)):
        raise TypeError(f"Custom strategy needs a name and {method} method")
    return spec


def resolve_diagnosis_strategy(spec: str | AssessmentDiagnosisStrategy = "error-family") -> AssessmentDiagnosisStrategy:
    return _resolve_strategy(spec, _DIAGNOSIS_STRATEGIES, "diagnose")


def resolve_learner_strategy(spec: str | LearnerStateStrategy = "repeated-error") -> LearnerStateStrategy:
    return _resolve_strategy(spec, _LEARNER_STRATEGIES, "recommend")
