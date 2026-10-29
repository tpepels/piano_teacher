"""Time-dependent practice transitions before graded note assessment.

The PracticeEngine still owns its lock, MIDI source, assessment and durable
state. This coordinator owns the ordered ungraded branches of each update tick.
It intentionally stops at the first applicable branch, so feedback, rewind,
preview and Listen cannot accidentally execute as one graded performance.
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


def phase(context: TransitionContext, now: float) -> str:
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
    # Preparation continues to update its public phase while feedback is
    # settling or score/meter acknowledgement has not arrived.
    if context.feedback_pending:
        return "feedback"
    if context.awaiting_score:
        return "awaiting_score"
    if context.rewind_pending:
        return "rewind"
    if not context.running or now < context.run_at:
        return "idle"
    return "performing"


def transition_context(engine) -> TransitionContext:
    return TransitionContext(
        has_plan=engine.plan is not None,
        learning=engine.mode == "learn" and engine.teaching is not None,
        paused=engine.paused,
        listening=engine.mode == "listen",
        preview_pending=engine._preview_loop_pending,
        preparation_pending=engine._preparation_pending,
        feedback_pending=engine.pending_result is not None,
        awaiting_score=engine.awaiting_score_revision is not None,
        rewind_pending=engine.pending_rewind is not None,
        running=engine.running,
        run_at=engine.run_at,
    )


def run_before_assessment(engine, now: float) -> bool:
    """Return True when the tick is consumed; False permits graded assessment.

    The caller samples the monotonic clock exactly once and retains the lock.
    Timeline continuations use the stored deadline, not wall-clock now.
    """
    context = transition_context(engine)
    selected = phase(context, now)
    if selected == "no_plan":
        return True
    if selected == "learning":
        engine.teaching.set_connected(engine.midi.connected, now=now)
        engine.teaching.tick(now=now)
        engine._save_guided_preparation()
        return True
    if selected == "paused":
        return True
    if selected == "listening":
        if engine.running and engine.listen.finished(now=now, run_at=engine.run_at):
            engine.running = False
            engine.feedback = "Example complete"
            engine.next_action = (
                "Choose Learn to find the notes, or Practice to play the rhythm.")
        return True
    if selected == "preview":
        if engine.next_at and now >= engine.next_at:
            deadline = engine.next_at
            engine.visual_offset_beats += engine._source_model()[
                "practice_timeline"]["stride_beats"]
            engine._continue_at(deadline)
        return True
    if context.preparation_pending:
        engine.practice_preparation["phase"] = (
            "reverse" if now < engine._preparation_at else "preparing")
    if selected == "feedback":
        engine._advance_pending_feedback(now)
        return True
    if selected == "awaiting_score":
        return True
    if selected == "rewind":
        if now >= engine.next_at:
            if engine._guided_recovery_pending:
                engine._begin_learn(from_beat=engine.pending_rewind, recovery=True)
            else:
                engine._continue_at(engine.next_at, from_beat=engine.pending_rewind)
        return True
    return selected != "performing"
