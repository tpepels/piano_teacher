"""Grade one completed take and prepare its visible feedback.

No engine access, transport mutation, persistence, or lesson routing.
Grading occurs before engraving lookup; if engraving projection fails, the
graded result is retained and reported as unmapped rather than discarded.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from ..exercise_contracts import TempoMap
from ..music import Phrase
from ..practice import Assessment, PlayedNote
from .practice_assessment import PracticeAssessmentPolicies
from ..completion_route import completion_route


@dataclass(frozen=True)
class AssessedTake:
    result: Assessment
    marks: list[dict]
    unmapped: int
    feedback: str


def assess_completed_take(
    *, phrase: Phrase, hand: str, bpm: float,
    played: Sequence[PlayedNote], from_beat: float, end_beat: float,
    tempo: TempoMap | None, policies: PracticeAssessmentPolicies,
    layout_for_feedback: Callable[[], dict],
) -> AssessedTake:
    """Grade first, then try to map feedback to the retained score layout."""
    result = policies.select(tempo).grade(
        phrase, hand=hand, bpm=bpm, played=played,
        from_beat=from_beat, end_beat=end_beat, tempo=tempo)
    try:
        projection = policies.project(
            result, phrase, bpm=bpm, layout=layout_for_feedback(),
            from_beat=from_beat, tempo=tempo)
        marks = projection["marks"]
        unmapped = projection["unmapped"]
    except (ValueError, RuntimeError, KeyError) as exc:
        return AssessedTake(
            result=result, marks=[], unmapped=len(result.notes),
            feedback=f"Engraving feedback unavailable: {exc}")
    return AssessedTake(
        result=result, marks=marks, unmapped=unmapped,
        feedback=result.summary)

@dataclass(frozen=True)
class CompletedTake:
    assessed: AssessedTake
    route: str
    summary: dict
    pending: object
    response: object
    settled: bool


def complete_grading_and_settlement(
    *, phrase: Phrase, hand: str, bpm: float,
    played: Sequence[PlayedNote], from_beat: float, end_beat: float,
    tempo: TempoMap | None, policies: PracticeAssessmentPolicies,
    layout_for_feedback: Callable[[], dict], mode: str,
    review_end_beat: float | None, automatic_remedial_review: bool,
    performance_review: Callable[[Phrase, Assessment], dict],
    prepare_decision: Callable, attempt, settlement, plan,
    binding, now: float, policy,
) -> CompletedTake:
    """One full/focused grading and evidence-settlement boundary.

    All routes use the same assessed notes and the same immutable decision;
    no progress, verdict or next exposure is reselected by the caller.
    Full-passage outcomes remain pending for their authorized successor
    boundary; focused/performance decisions settle immediately.
    """
    assessed = assess_completed_take(
        phrase=phrase,hand=hand,bpm=bpm,played=played,
        from_beat=from_beat,end_beat=end_beat,tempo=tempo,
        policies=policies,layout_for_feedback=layout_for_feedback)
    result = assessed.result
    route = completion_route(mode,review_end_beat,from_beat)
    if automatic_remedial_review and route == "section_review":
        route = "partial_recovery"
    summary = performance_review(phrase,result)
    if route == "full_passage":
        attempt.hold_full_result(result,bpm)
        pending = prepare_decision("full_result",result)
        response = None
    else:
        pending = prepare_decision("focused_result",result,end_beat=end_beat)
        response = pending.decision.response
    settled = settlement.seal_completed_take(
        pending,played=played,route=route,mode=mode,
        at_target=bpm >= plan.target_bpm,
        assessed_end_beat=end_beat,result=result,plan=plan,
        binding=binding,now=now,policy=policy,performance_summary=summary)
    return CompletedTake(assessed,route,summary,pending,response,settled)
