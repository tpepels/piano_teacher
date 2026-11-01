"""Commit graded evidence and advance one lesson stage under the caller's lock.

This operation deliberately mutates the supplied LearningPlan and writes
adaptive assessment evidence. It does not own PracticeEngine, transport,
score revisions, feedback presentation, or session-file persistence.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .assessment_evidence import observe_assessed_take


@dataclass(frozen=True)
class AssessmentCommit:
    message: str
    previous_stage: str
    previous_bpm: float
    stage_changed: bool
    accelerated: bool
    remediation: Any | None


def commit_assessed_result(
    *, plan, result, fingerprint: str, automatic: bool,
    mode: str, warmup: bool,
    observe: Callable[..., Any],
    plan_remediation: Callable[..., Any],
) -> AssessmentCommit:
    """Use the original stage identity for evidence before applying mastery."""
    stage = plan.identity
    bpm = plan.bpm
    accepted = getattr(result, "passed", result.clean)
    recommendation = observe_assessed_take(
        fingerprint=fingerprint, stage_key=stage, bpm=bpm,
        result=result, observe=observe)
    message = plan.apply_result(
        correct=result.correct, total=len(result.notes),
        extras=result.extra_notes, accepted=accepted)
    remediation = None
    if (recommendation is not None and not accepted and automatic
            and mode == "practice" and not warmup
            and plan.exercise.kind == "learn" and plan.identity == stage):
        remediation = plan_remediation(
            recommendation, result, plan.active_variant,
            stage_key=stage, boundaries=plan.piece.bar_boundaries)
    return AssessmentCommit(
        message=message, previous_stage=stage, previous_bpm=bpm,
        stage_changed=plan.identity != stage,
        accelerated=plan.identity == stage and plan.bpm > bpm,
        remediation=remediation)
