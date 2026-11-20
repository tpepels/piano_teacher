"""Pure completion routing for post-performance practice decisions.

A partial recovery never grants mastery. Explicit performance and section
review routes take precedence over full-passage practice; preview never grades.
No transport clocks, persistence, renderers or live engine state are accessed.
"""
from __future__ import annotations

from typing import Literal
from dataclasses import dataclass

CompletionRoute = Literal["perform", "section_review", "partial_recovery", "full_passage"]


def completion_route(mode: str, review_end_beat: float | None,
                     play_from_beat: float) -> CompletionRoute:
    if mode == "perform":
        return "perform"
    if review_end_beat is not None:
        return "section_review"
    if play_from_beat > 1e-6:
        return "partial_recovery"
    return "full_passage"


@dataclass(frozen=True, slots=True)
class CompletionEffect:
    action: str
    exposure: object = None
    response: object = None


def completion_effect(route: CompletionRoute, decision) -> CompletionEffect:
    """Dispatch one selected teaching consequence; never select another."""
    if decision.response is not None and route != "full_passage":
        return CompletionEffect("response",response=decision.response)
    if route == "partial_recovery":
        if decision.continuation in ("stop","pause"):
            return CompletionEffect("stop_review")
        exposure = decision.next_exposure
        return CompletionEffect("exposure" if exposure.mode == "learn"
                                else "partial_recovery",exposure=exposure)
    return CompletionEffect(route)
