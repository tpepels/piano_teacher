"""Required notes must have a unique matching engraved notehead."""
import pytest
from piano_teacher.lesson_validation import missing_engraved_notes, require_lesson_alignment
from piano_teacher.music import Note, Phrase


def test_matching_quantized_and_repeated_pitch():
    notes=(Note(0,.5,60,0,0,"right"),Note(1,1.5,60,0,0,"right"))
    phrase=Phrase(1,1,2,0,8,notes)
    assert not missing_engraved_notes(phrase,{"notes":[
        {"pitch":60,"beat":.02},{"pitch":60,"beat":1.01}]},"right")


def test_duplicate_unison_needs_two_noteheads():
    notes=(Note(0,.5,60,0,0,"right"),Note(0,.5,60,1,0,"right"))
    phrase=Phrase(1,1,2,0,8,notes)
    with pytest.raises(ValueError,match="omitted 1 required"):
        require_lesson_alignment(phrase,{"notes":[{"pitch":60,"beat":0}]},"right")


def test_other_hand_not_required_for_single_hand_exercise():
    notes=(Note(0,.5,60,0,0,"right"),Note(0,.5,48,1,0,"left"))
    phrase=Phrase(1,1,2,0,8,notes)
    assert not missing_engraved_notes(phrase,
        {"notes":[{"pitch":60,"beat":0}]},"right")
