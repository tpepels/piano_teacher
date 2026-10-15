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


def test_long_chord_only_marks_missing_pitch_before_expected_releases():
    from piano_teacher.live_feedback import expired_attack_misses
    chord = Phrase(1, 1, 2, 0, 8, (
        Note(0, 2, 60, 0, 0, "right", "c"),
        Note(0, 2, 64, 0, 0, "right", "e"),
        Note(0, 2, 67, 0, 0, "right", "g"),
    ))
    played = [PlayedNote(60, 0, None), PlayedNote(64, .03, None)]
    assert expired_attack_misses(chord, "right", 60, played,
                                from_beat=0, until_beat=.60) is None
    missing = expired_attack_misses(chord, "right", 60, played,
                                    from_beat=0, until_beat=.72)
    assert [(m.note.pitch, m.status) for m in missing.notes] == [(67, "missed")]


def test_wrong_pitch_does_not_hide_missing_chord_note():
    from piano_teacher.live_feedback import expired_attack_misses
    chord = Phrase(1, 1, 2, 0, 8, (
        Note(0, 1.8, 60, 0, 0, "right", "c"),
        Note(0, 1.8, 64, 0, 0, "right", "e"),
    ))
    played = [PlayedNote(60, .02, .5), PlayedNote(63, .03, .4)]
    missing = expired_attack_misses(chord, "right", 60, played,
                                    from_beat=0, until_beat=.72)
    assert [(m.note.pitch, m.status) for m in missing.notes] == [(64, "missed")]


def test_repeated_same_pitch_does_not_let_one_keypress_clear_two_misses():
    from piano_teacher.live_feedback import expired_attack_misses
    notes = (Note(0, .4, 60, 0, 0, "right"),
             Note(.5, 1, 60, 0, 0, "right"))
    phrase = Phrase(1, 1, 2, 0, 4, notes)
    missed = expired_attack_misses(phrase, "right", 120,
                                  [PlayedNote(60, 0, .4)],
                                  from_beat=0, until_beat=2)
    assert [(n.note.start, n.status) for n in missed.notes] == [(.5, "missed")]


def test_wrong_or_missing_notes_can_trigger_warmup_boundary_recovery():
    from piano_teacher.recovery import check_two_bar_window
    chord = Phrase(1, 1, 2, 0, 8, (
        Note(0, 2, 60, 0, 0, "left"),
        Note(0, 2, 64, 0, 0, "left"),
        Note(0, 2, 67, 0, 0, "left"),
    ))
    played = [PlayedNote(60, 0, 2)]
    assert check_two_bar_window(chord, "left", 60, played,
                                from_beat=0, end_beat=4, beats_per_bar=2,
                                threshold=5) is None
    decision = check_two_bar_window(chord, "left", 60, played,
                                    from_beat=0, end_beat=4, beats_per_bar=2,
                                    threshold=2)
    assert decision is not None
    assert (decision.missed, decision.wrong) == (2, 0)
