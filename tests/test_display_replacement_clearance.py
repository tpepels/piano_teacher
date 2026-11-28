"""Replacement must use geometry from the failed, authenticated exposure."""
from types import SimpleNamespace
from unittest.mock import Mock
import pytest

from piano_teacher.application.transport_actions import PlaybackAuthorization


def authorization():
    transport = Mock()
    transport.mode = "practice"
    transport.running = True
    transport.paused = False
    timing = Mock()
    calls = []
    transport.fail.side_effect = lambda **kw: calls.append("failed")
    timing.update_placement_facts.side_effect = lambda facts: calls.append(("geometry", facts))
    transport.clear_failure.side_effect = lambda: calls.append("cleared")
    timing.request_playback.side_effect = lambda **kw: calls.append("replacement")
    owner = PlaybackAuthorization(
        lesson=SimpleNamespace(plan=SimpleNamespace(identity="step"), fingerprint="score",
                               revision=7, opening_beat=0.),
        transport=transport, transport_timing=timing, timed_start=None,
        pause_resume=None, lifecycle=None, listen=None, presentation=None,
        notices=None, clock=lambda: 10.)
    return owner, calls


def test_replacement_accepts_fresh_geometry_after_revocation():
    owner, calls = authorization()
    placement = {"placement_revision": 7, "ink_ahead_beats": 1.25}
    owner.fail_physical(take_id="take", segment_id="segment",
                        reason="timeline_take_not_drawn", placement=placement)
    assert calls == ["failed", ("geometry", placement), "cleared", "replacement"]
    assert "placement" not in owner.transport.fail.call_args.kwargs


def test_stale_failure_cannot_change_placement():
    owner, calls = authorization()
    owner.transport.fail.side_effect = ValueError("Stale playback failure")
    with pytest.raises(ValueError, match="Stale"):
        owner.fail_physical(take_id="old", segment_id="old",
                            reason="timeline_take_not_drawn",
                            placement={"placement_revision": 7, "ink_ahead_beats": 100})
    assert calls == []


def test_nonreplaceable_failure_cannot_change_placement():
    owner, calls = authorization()
    owner.fail_physical(take_id="take", segment_id="segment",
                        reason="presentation_timeout",
                        placement={"placement_revision": 7, "ink_ahead_beats": 100})
    assert calls == ["failed"]
