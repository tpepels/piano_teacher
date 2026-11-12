"""Explicit transport command precedence and musical deadline routing."""
from dataclasses import replace

import pytest

from piano_teacher.application.transport_commands import (
    StartFacts, require_pausable, resume_timeline, select_start_route,
)


START = StartFacts(
    action="start", mode="practice", loaded=True,
    source_changed=False, exercise_kind="learn")


@pytest.mark.parametrize(("changes", "expected"), [
    ({}, "start"),
    ({"mode":"listen"}, "listen"),
    ({"mode":"learn"}, "prepare_practice"),
    ({"source_changed":True}, "reload_score"),
    ({"action":"restart"}, "rewind"),
    ({"action":"restart","exercise_kind":"perform"}, "start"),
    ({"action":"restart","mode":"perform"}, "start"),
    ({"action":"restart","loaded":False}, "start"),
    ({"mode":"listen","source_changed":True}, "listen"),
    ({"mode":"learn","source_changed":True}, "prepare_practice"),
    ({"action":"restart","source_changed":True}, "reload_score"),
])
def test_start_precedence(changes, expected):
    assert select_start_route(replace(START, **changes)) == expected


@pytest.mark.parametrize("phase", (
    "playing", "count_in", "feedback", "recovering",
    "loading", "guided_wait", "preview_gap"))
def test_each_active_phase_is_pausable(phase):
    require_pausable(paused=False, phase=phase)


@pytest.mark.parametrize("phase", ("idle", "ready", "guided_complete", ""))
def test_inactive_or_already_paused_sessions_reject_pause(phase):
    with pytest.raises(ValueError, match="Cannot pause unless"):
        require_pausable(paused=False, phase=phase)
    with pytest.raises(ValueError, match="already paused"):
        require_pausable(paused=True, phase=phase)


@pytest.mark.parametrize(("inputs", "expected"), [
    ({"running":True}, True),
    ({"preview_pending":True}, True),
    ({"automatic_feedback":True}, True),
    ({"learning":True, "running":True}, False),
    ({}, False),
])
def test_resume_shifts_only_running_non_guided_deadlines(inputs, expected):
    facts = {"paused":True,"learning":False,"running":False,
             "preview_pending":False,"automatic_feedback":False}
    assert resume_timeline(**{**facts,**inputs}) is expected
    with pytest.raises(ValueError, match="unless an exercise is paused"):
        resume_timeline(**{**facts, **inputs, "paused":False})



@pytest.mark.parametrize(("lead","rest","minimum","expected"), [
    (14.0,6.0,1.0,8.0),
    (7.0,6.0,1.0,1.0),
    (3.5,3.0,0.1,0.5),
    # Round 4: the reserved deadline wins over the reverse animation's
    # nominal minimum (a Retry is never pushed later than its ink).
    (7.0,6.0,2.0,1.0),
])
def test_retry_reading_lead_accounts_for_written_rest_once(lead, rest, minimum, expected):
    from piano_teacher.application.transport_commands import planned_retry_reverse_seconds
    assert planned_retry_reverse_seconds(
        reading_lead_seconds=lead,
        semantic_rest_seconds=rest,
        minimum_rewind_seconds=minimum) == pytest.approx(expected)


@pytest.mark.parametrize(("lead","rest","minimum"), [
    (4.0,6.0,1.0),
    (6.02,6.0,2.0),
    (float("nan"),4.0,1.0),
    (8.0,0.0,1.0),
])
def test_retry_reservation_fails_closed_if_rest_or_reading_lead_cannot_fit(
        lead, rest, minimum):
    from piano_teacher.application.transport_commands import planned_retry_reverse_seconds
    with pytest.raises(ValueError, match="retry"):
        planned_retry_reverse_seconds(
            reading_lead_seconds=lead,
            semantic_rest_seconds=rest,
            minimum_rewind_seconds=minimum)
