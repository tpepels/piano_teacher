"""Two-measure recovery: wrong vs missed pitch, window and hand filtering."""
from piano_teacher.music import Note, Phrase
from piano_teacher.practice import PlayedNote
from piano_teacher.recovery import check_two_bar_window


def phrase():
    notes = tuple(Note(float(i), float(i)+.5, 60+i, 0, 0, "right") for i in range(8))
    return Phrase(1, 1, 2, 0, 8, notes)


def test_five_missing_notes_trigger_rewind():
    played = [PlayedNote(60+i, i*.5, (i+.5)*.5) for i in (0,1,2)]
    decision = check_two_bar_window(phrase(), "right", 120, played, from_beat=0,
                                    end_beat=8, beats_per_bar=4)
    assert decision.errors == 5 and decision.restart_beat == 0


def test_four_misses_do_not_trigger_retry():
    played = [PlayedNote(60+i, i*.5, (i+.5)*.5) for i in (0,1,2,3)]
    assert check_two_bar_window(phrase(), "right", 120, played, from_beat=0,
                                end_beat=8, beats_per_bar=4) is None


def test_wrong_note_does_not_count_twice():
    played = [PlayedNote(90, 0, .25)] + [
        PlayedNote(60+i, i*.5, (i+.5)*.5) for i in (1,2,3)]
    decision = check_two_bar_window(phrase(), "right", 120, played, from_beat=0,
                                    end_beat=8, beats_per_bar=4)
    assert decision.errors == 5 and decision.wrong == 1 and decision.missed == 4


def test_four_bar_rewind_selects_last_two_bars():
    notes = tuple(Note(float(i), float(i)+.5, 60+i, 0, 0, "right") for i in range(16))
    passage = Phrase(1,1,4,0,16,notes)
    decision = check_two_bar_window(passage, "right", 120, [], from_beat=8,
                                    end_beat=16, beats_per_bar=4)
    assert decision.restart_beat == 8 and decision.errors == 8


def test_other_hand_does_not_trigger_rewind():
    notes = tuple(Note(n.start,n.end,n.pitch,n.track,n.channel,"left") for n in phrase().notes)
    passage = Phrase(1,1,2,0,8,notes)
    assert check_two_bar_window(passage,"right",120,[],from_beat=0,
                                end_beat=8,beats_per_bar=4) is None
