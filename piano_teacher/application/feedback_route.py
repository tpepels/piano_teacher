"""Pure routing after assessed feedback has been committed.

Only PracticeEngine applies the resulting transition. This module makes
remediation, guided progression, score revision acknowledgement, and retry
precedence independently testable without a mutable engine dependency.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

FeedbackRoute = Literal[
    "remediation", "guided_stage", "await_score", "continue", "stop"
]


@dataclass(frozen=True)
class FeedbackFacts:
    automatic: bool
    has_remediation: bool
    same_stage: bool
    course_guided: bool
    score_changed: bool
    message: str


def select_feedback_route(facts: FeedbackFacts) -> FeedbackRoute:
    if facts.automatic and facts.has_remediation and facts.same_stage:
        return "remediation"
    if not facts.automatic or facts.message == "Piece mastered":
        return "stop"
    if facts.course_guided and not facts.same_stage:
        return "guided_stage"
    if facts.score_changed:
        return "await_score"
    return "continue"
