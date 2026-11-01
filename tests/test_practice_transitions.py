"""Pure transition precedence; no PracticeEngine is available to this policy."""
from dataclasses import replace

import pytest

from piano_teacher.application.practice_transitions import (
    TransitionContext, decide_transition, phase,
)


BASE = TransitionContext(
    has_plan=True, learning=False, paused=False, listening=False,
    preview_pending=False, preparation_pending=False, feedback_pending=False,
    awaiting_score=False, rewind_pending=False, running=True, run_at=100.0)


@pytest.mark.parametrize(("changes", "expected"), [
    ({}, "performing"),
    ({"has_plan": False}, "no_plan"),
    ({"learning": True}, "learning"),
    ({"paused": True}, "paused"),
    ({"listening": True}, "listening"),
    ({"preview_pending": True}, "preview_wait"),
    ({"feedback_pending": True}, "feedback"),
    ({"awaiting_score": True}, "awaiting_score"),
    ({"rewind_pending": True}, "rewind_wait"),
    ({"running": False}, "idle"),
    ({"run_at": 105.0}, "idle"),
    ({"paused": True, "feedback_pending": True}, "paused"),
    ({"learning": True, "paused": True}, "learning"),
    ({"listening": True, "preview_pending": True}, "listening"),
    ({"preview_pending": True, "feedback_pending": True}, "preview_wait"),
    ({"feedback_pending": True, "awaiting_score": True}, "feedback"),
    ({"awaiting_score": True, "rewind_pending": True}, "awaiting_score"),
])
def test_precedence(changes, expected):
    context = replace(BASE, **changes)
    decision = decide_transition(
        context, now=101.0, next_at=105.0, preparation_at=102.0)
    assert decision.action == expected
    assert decision.consumed == (expected != "performing")


def test_absolute_deadlines_do_not_shift_with_polling():
    preview = replace(BASE, preview_pending=True)
    rewind = replace(BASE, rewind_pending=True)
    assert decide_transition(preview, now=104.99, next_at=105.0,
                             preparation_at=0.0).action == "preview_wait"
    assert decide_transition(preview, now=105.0, next_at=105.0,
                             preparation_at=0.0).action == "preview_due"
    assert decide_transition(rewind, now=104.99, next_at=105.0,
                             preparation_at=0.0).action == "rewind_wait"
    assert decide_transition(rewind, now=105.0, next_at=105.0,
                             preparation_at=0.0).action == "rewind_due"


def test_preparation_projection_does_not_override_grading_precedence():
    context = replace(BASE, preparation_pending=True)
    assert decide_transition(context, now=101.0, next_at=110.0,
                             preparation_at=102.0).preparation_phase == "reverse"
    assert decide_transition(context, now=102.0, next_at=110.0,
                             preparation_at=102.0).preparation_phase == "preparing"
    for held in ("paused", "listening", "preview_pending", "learning"):
        frozen = replace(context, **{held: True})
        assert decide_transition(frozen, now=101.0, next_at=110.0,
                                 preparation_at=102.0).preparation_phase is None
    feedback = replace(context, feedback_pending=True)
    result = decide_transition(feedback, now=101.0, next_at=110.0,
                               preparation_at=102.0)
    assert result.action == "feedback" and result.preparation_phase == "reverse"


def test_phase_is_a_pure_selector():
    assert phase(BASE, 101.0) == "performing"
    assert phase(BASE, 99.0) == "idle"
