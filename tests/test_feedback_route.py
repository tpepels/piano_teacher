"""Feedback routing precedence is independent of the mutable practice engine."""
from dataclasses import replace

import pytest

from piano_teacher.application.feedback_route import (
    FeedbackFacts, select_feedback_route,
)


BASE = FeedbackFacts(
    automatic=True, has_remediation=False, same_stage=True,
    coda=False, course_guided=False, score_changed=False, message="Continue")


@pytest.mark.parametrize(("updates", "expected"), [
    ({}, "continue"),
    ({"has_remediation": True}, "remediation"),
    ({"has_remediation": True, "coda": True}, "continue"),
    ({"has_remediation": True, "same_stage": False}, "continue"),
    ({"course_guided": True, "same_stage": False}, "guided_stage"),
    ({"score_changed": True}, "await_score"),
    ({"score_changed": True, "has_remediation": True}, "remediation"),
    ({"course_guided": True, "same_stage": False, "score_changed": True},
     "guided_stage"),
    ({"automatic": False}, "stop"),
    ({"message": "Piece mastered"}, "stop"),
    ({"automatic": False, "has_remediation": True}, "stop"),
    ({"message": "Piece mastered", "has_remediation": True}, "remediation"),
])
def test_feedback_routes(updates, expected):
    assert select_feedback_route(replace(BASE, **updates)) == expected


def test_feedback_route_never_mutates_inputs():
    initial = BASE
    assert select_feedback_route(initial) == "continue"
    assert initial == BASE
