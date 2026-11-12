"""Record trustworthy completed-take evidence without owning lesson state.

Only actual assessed note records may update adaptive practice history.
The caller supplies the bound observation write; stage selection, mastery,
feedback settlement and persistent session save remain in PracticeEngine.
"""
from __future__ import annotations

from typing import Any, Callable

from ..diagnosis_policies import AssessmentEvidence


def observe_assessed_take(
    *, fingerprint: str, stage_key: str, bpm: float, result: Any,
    observe: Callable[[str, AssessmentEvidence], Any],
) -> Any | None:
    notes = getattr(result, "notes", None)
    if not fingerprint or not notes or not all(
            hasattr(entry, "status") for entry in notes):
        return None
    evidence = AssessmentEvidence.from_result(stage_key, result, bpm)
    return observe(fingerprint, evidence)
