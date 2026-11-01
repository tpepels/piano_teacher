"""Score acknowledgements never advance stale, paused, or wrong-mode scores."""
from dataclasses import replace

import pytest

from piano_teacher.application.score_ack import (
    ScoreAckState, choose_score_ack_action,
)

READY = ScoreAckState(
    requested_revision=7, current_revision=7,
    paused=False, mode="practice", teaching_bound=False)


@pytest.mark.parametrize(("change","expected"),[
    ({}, "practice"),
    ({"mode":"perform"}, "practice"),
    ({"mode":"listen"}, "listen"),
    ({"mode":"learn","teaching_bound":True}, "learn"),
    ({"mode":"learn","teaching_bound":False}, "practice"),
    ({"paused":True}, "defer"),
    ({"mode":"listen","paused":True}, "defer"),
    ({"mode":"learn","teaching_bound":True,"paused":True}, "defer"),
    ({"requested_revision":None}, "ignore"),
    ({"current_revision":8}, "ignore"),
])
def test_score_ack_precedence(change, expected):
    assert choose_score_ack_action(7,replace(READY,**change)) == expected


def test_stale_ack_ignored_even_if_listen_or_guided():
    for mode in ("learn","listen","practice"):
        state=replace(READY,mode=mode,teaching_bound=True)
        assert choose_score_ack_action(6,state) == "ignore"
        assert choose_score_ack_action(8,state) == "ignore"
