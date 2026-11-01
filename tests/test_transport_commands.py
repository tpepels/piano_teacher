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
    with pytest.raises(ValueError, match="already paused"):
        resume_timeline(**{**facts, **inputs, "paused":False})
