"""Source-bar Seek must keep its selected mode through score_ready.

The same TeachingExposure is reused by the asynchronous native score-ack
path. Perform -> Seek must produce a bounded Practice attempt rather than
re-enter Perform after a score revision is acknowledged.
"""
from types import SimpleNamespace

import pytest

from piano_teacher.music import Phrase
from piano_teacher.teaching_manual import choose_manual


@pytest.mark.parametrize("previous_mode", ["perform", "practice"])
def test_seek_from_timed_mode_prepares_practice_exposure(previous_mode):
    phrase = Phrase(1, 1, 4, 0, 16, ())
    course = SimpleNamespace(
        stage=SimpleNamespace(variant=SimpleNamespace(phrase=phrase)),
        piece=SimpleNamespace(bar_boundaries=(0, 4, 8, 12, 16)),
    )
    state = SimpleNamespace(
        course=course,
        route=SimpleNamespace(mode=previous_mode),
        manual_facts=SimpleNamespace(open_from_beat=0.0, paused=True),
    )
    event = SimpleNamespace(action="seek", manual=None, bar=3)
    chosen, start, end, mode, continuation = choose_manual(event, state)
    assert chosen is course
    assert start == 8
    assert end is None
    assert mode == "practice"
    assert continuation == "continue"


def test_seek_does_not_convert_unpaused_performance_to_practice():
    phrase = Phrase(1, 1, 4, 0, 16, ())
    state = SimpleNamespace(
        course=SimpleNamespace(
            stage=SimpleNamespace(variant=SimpleNamespace(phrase=phrase)),
            piece=SimpleNamespace(bar_boundaries=(0, 4, 8, 12, 16)),
        ),
        route=SimpleNamespace(mode="perform"),
        manual_facts=SimpleNamespace(open_from_beat=0.0, paused=False),
    )
    with pytest.raises(ValueError, match="Pause"):
        choose_manual(SimpleNamespace(action="seek", manual=None, bar=3), state)
