"""Immutable future-score identity under Pause/Resume and withdrawal."""
from types import SimpleNamespace

import pytest

from piano_teacher.application.teaching_continuation import TeachingContinuation
from piano_teacher.visual_transport import VisualTransport


def pending(*, from_beat=0.0, bpm=40.0, decision_id="take:next"):
    exposure = SimpleNamespace(from_beat=from_beat, bpm=bpm)
    return SimpleNamespace(decision=SimpleNamespace(
        decision_id=decision_id, next_exposure=exposure))


def test_resume_retimes_existing_announced_score_without_new_plan_identity():
    transport = VisualTransport()
    continuation = TeachingContinuation(None, transport)
    take = pending()
    continuation.announce(take, deadline=130.0)
    serial = transport.announce_serial
    transport.pause(at=110.0)
    transport.resume(now=120.0, shift_run_at=False)
    # The engine's visual deadline changed while its admitted ink survived.
    continuation.announce(take, deadline=135.0)
    assert transport.announce_serial == serial
    assert transport.announced_continuation == (0.0, 135.0, 40.0)
    assert continuation.schedule.run_at == 135.0
    continuation.validate_announcement(take)


def test_withdrawing_future_copy_allows_settlement_and_new_admission():
    transport = VisualTransport()
    continuation = TeachingContinuation(None, transport)
    take = pending()
    continuation.announce(take, deadline=130.0)
    old_serial = transport.announce_serial
    # The future suffix is explicitly retracted before grading/settlement.
    transport.announced_continuation = None
    continuation.validate_announcement(take)
    assert continuation.schedule is None
    assert transport.announced_deadline(0.0) is None
    continuation.announce(take, deadline=140.0)
    assert transport.announce_serial == old_serial + 1
    assert transport.announced_deadline(0.0) == 140.0


def test_changed_exposure_cannot_steal_admitted_score_identity():
    transport = VisualTransport()
    continuation = TeachingContinuation(None, transport)
    take = pending()
    continuation.announce(take, deadline=130.0)
    serial = transport.announce_serial
    changed = pending(from_beat=8.0, decision_id="take:next")
    with pytest.raises(ValueError, match="exposure changed"):
        continuation.announce(changed, deadline=130.0)
    assert transport.announce_serial == serial
    with pytest.raises(ValueError, match="exposure changed"):
        continuation.validate_announcement(changed)


def test_mismatched_announcement_deadline_fails_closed():
    transport = VisualTransport()
    continuation = TeachingContinuation(None, transport)
    take = pending()
    continuation.announce(take, deadline=130.0)
    transport.retime_announcement(131.0)
    with pytest.raises(ValueError, match="no longer matches"):
        continuation.validate_announcement(take)
