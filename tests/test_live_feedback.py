"""Live musical feedback must wait for note release and avoid future notes."""
import pytest
from piano_teacher.live_feedback import settled_assessment
from piano_teacher.music import Note, Phrase
from piano_teacher.practice import PlayedNote


def phrase():
    notes=(Note(0,.5,60,0,0,"right"),Note(1,1.5,62,0,0,"right"),
           Note(2,2.5,64,0,0,"right"),Note(0,.5,48,1,0,"left"))
    return Phrase(1,1,2,0,8,notes)


def assess(played,now,from_beat=0,hand="right"):
    return settled_assessment(phrase(),hand,60,played,from_beat=from_beat,
                              until_beat=now,beats_per_bar=4)


def test_no_premature_miss_for_held_or_upcoming_notes():
    assert assess([], .5) is None
    result=assess([], .63)
    assert result is not None
    assert [(e.note.pitch,e.status) for e in result.notes] == [(60,"missed")]


def test_pitch_and_duration_checked_after_settling():
    result=assess([PlayedNote(60,0,.5)],.7)
    assert [(n.note.pitch,n.status) for n in result.notes] == [(60,"correct")]
    assert result.extra_notes==0


def test_wrong_pitch_is_not_double_counted_as_extra():
    result=assess([PlayedNote(72,0,.5)],.8)
    assert [(n.note.pitch,n.status) for n in result.notes] == [(60,"wrong")]
    assert result.extra_notes==0


def test_prerecorded_future_notes_are_not_presented_as_live_errors():
    result=assess([PlayedNote(60,0,.5),PlayedNote(64,2,2.5)],.8)
    assert [n.status for n in result.notes]==["correct"]
    assert result.extra_notes==0
    assert result.unmatched_played==()


def test_filters_inactive_hand():
    result=assess([], .7,hand="left")
    assert len(result.notes)==1
    assert result.notes[0].note.pitch==48


def test_invalid_music_clock_parameters():
    with pytest.raises(ValueError):
        settled_assessment(phrase(),"both",0,[],from_beat=0,
                           until_beat=2,beats_per_bar=4)
