"""Guided source-fragment boundaries are independent of teaching state."""
import pytest

from piano_teacher.application.guided_fragment import select_guided_fragment
from piano_teacher.music import Note, Phrase


def test_skips_silent_opening_two_bar_unit():
    notes = (Note(8, 8.5, 60, 0, 0, "right"),)
    phrase = Phrase(1, 1, 3, 0, 12, notes)
    selected = select_guided_fragment(phrase, (0, 4, 8, 12), 0)
    assert selected.first_index == 2
    assert selected.end_index == 3
    assert (selected.start, selected.end) == (8, 12)


def test_keeps_original_source_meter_boundary():
    notes = (Note(3, 3.5, 60, 0, 0, "right"),
             Note(8, 8.5, 62, 0, 0, "right"))
    phrase = Phrase(1, 1, 3, 0, 10, notes)
    first = select_guided_fragment(phrase, (0, 3, 7, 10), 0)
    last = select_guided_fragment(phrase, (0, 3, 7, 10), 7)
    assert (first.start, first.end) == (0, 7)
    assert (last.start, last.end) == (7, 10)


@pytest.mark.parametrize("beat", (-1, 12, float("nan"), float("inf")))
def test_invalid_start_is_rejected(beat):
    notes = (Note(0, 1, 60, 0, 0, "right"),)
    phrase = Phrase(1, 1, 3, 0, 12, notes)
    with pytest.raises(ValueError, match="Choose a measure"):
        select_guided_fragment(phrase, (0, 4, 8, 12), beat)


def test_entirely_silent_source_cannot_begin_guided_lesson():
    phrase = Phrase(1, 1, 2, 0, 8, ())
    with pytest.raises(ValueError, match="No note attacks"):
        select_guided_fragment(phrase, (0, 4, 8), 0)
