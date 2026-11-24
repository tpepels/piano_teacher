"""Pure precedence and deadline decisions for ungraded practice transitions.

The engine owns its lock, transport, teaching, MIDI and durable state. This
module never receives the engine or executes an effect. The preparation phase
is independent of the selected branch, matching the original tick semantics.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TransitionContext:
    has_plan: bool
    learning: bool
    paused: bool
    listening: bool
    feedback_pending: bool
    awaiting_score: bool
    rewind_pending: bool
    running: bool
    run_at: float


@dataclass(frozen=True)
class TransitionDecision:
    action: str
    consumed: bool


def phase(context: TransitionContext, now: float) -> str:
    """First applicable transition, ordered by musical state precedence."""
    if not context.has_plan:
        return "no_plan"
    if context.learning:
        return "learning"
    if context.paused:
        return "paused"
    if context.listening:
        return "listening"
    if context.feedback_pending:
        return "feedback"
    if context.awaiting_score:
        return "awaiting_score"
    if context.rewind_pending:
        return "rewind"
    if not context.running or now < context.run_at:
        return "idle"
    return "performing"


def decide_transition(context: TransitionContext, *, now: float) -> TransitionDecision:
    selected = phase(context, now)
    if selected == "rewind":
        selected = "rewind_due"
    return TransitionDecision(selected, selected != "performing")
