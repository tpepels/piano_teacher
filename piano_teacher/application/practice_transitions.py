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
    preview_pending: bool
    preparation_pending: bool
    feedback_pending: bool
    awaiting_score: bool
    rewind_pending: bool
    running: bool
    run_at: float


@dataclass(frozen=True)
class TransitionDecision:
    action: str
    consumed: bool
    preparation_phase: str | None = None


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
    if context.preview_pending:
        return "preview"
    if context.feedback_pending:
        return "feedback"
    if context.awaiting_score:
        return "awaiting_score"
    if context.rewind_pending:
        return "rewind"
    if not context.running or now < context.run_at:
        return "idle"
    return "performing"


def decide_transition(context: TransitionContext, *, now: float,
                      next_at: float, preparation_at: float) -> TransitionDecision:
    selected = phase(context, now)
    # Earlier branches return without changing preparation presentation.
    preparation = None
    if context.preparation_pending and selected not in (
            "no_plan", "learning", "paused", "listening", "preview"):
        preparation = "reverse" if now < preparation_at else "preparing"
    if selected == "preview":
        selected = "preview_due" if next_at and now >= next_at else "preview_wait"
    elif selected == "rewind":
        selected = "rewind_due" if now >= next_at else "rewind_wait"
    return TransitionDecision(selected, selected != "performing", preparation)
