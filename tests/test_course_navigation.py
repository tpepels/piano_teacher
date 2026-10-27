"""Navigation chooses a playable source measure without changing the plan."""
from types import SimpleNamespace as Obj

import pytest

from piano_teacher.course_navigation import locate_course_section


def _plan(onsets):
    return Obj(
        piece=Obj(bar_boundaries=(0, 3, 6, 9, 12),
                  notes=tuple(Obj(start=beat) for beat in onsets)),
        exercises=(
            Obj(kind="learn", phrase=Obj(first_bar=1, last_bar=2)),
            Obj(kind="perform", phrase=Obj(first_bar=1, last_bar=4)),
            Obj(kind="learn", phrase=Obj(first_bar=3, last_bar=4)),
        ),
    )


def test_silent_first_measure_advances_to_playable_section():
    plan = _plan((3.5, 9.5))
    index, section, bar = locate_course_section(plan, 1)
    assert (index, section, bar) == (0, plan.exercises[0], 2)
    assert len(plan.exercises) == 3


def test_silent_later_measure_preserves_source_measure_number():
    plan = _plan((3.5, 9.5))
    index, section, bar = locate_course_section(plan, 3)
    assert (index, section, bar) == (2, plan.exercises[2], 4)


def test_last_measure_with_no_future_notes_is_rejected():
    with pytest.raises(ValueError, match="No playable notes"):
        locate_course_section(_plan((3.5,)), 4)


def test_perform_sections_do_not_replace_teaching_sections():
    plan = _plan((0.5, 6.2))
    index, section, bar = locate_course_section(plan, 3)
    assert (index, section, bar) == (2, plan.exercises[2], 3)
