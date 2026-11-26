from piano_teacher.music import Note, Phrase
from piano_teacher.practice import PlayedNote, evaluate
from piano_teacher.live_feedback import live_assessment


def passage(*notes):
    return Phrase(1, 1, 1, 0, 4, tuple(
        Note(beat, beat+0.1, pitch, 0, 0, "right")
        for beat, pitch in notes))


def test_late_cannot_correct_previous_note_after_next_onset():
    phrase = passage((0, 60), (0.1, 62))
    attacks = [PlayedNote(62, .1, .2), PlayedNote(60, .12, .22)]
    result = evaluate(phrase, "right", 60, attacks)
    assert [n.status for n in result.notes] == ["missed", "correct"]
    assert result.extra_notes == 1


def test_exact_next_onset_is_exclusive_for_previous_note():
    phrase = passage((0, 60), (.1, 62))
    result = evaluate(phrase, "right", 60, [PlayedNote(60, .1, .2)])
    assert result.notes[0].status == "missed"
    assert result.notes[1].status == "wrong"


def test_chord_notes_share_next_distinct_onset():
    phrase = passage((0, 60), (0, 64), (.2, 67))
    result = evaluate(phrase, "right", 60, [
        PlayedNote(60, .02, .1), PlayedNote(64, .04, .1),
        PlayedNote(67, .2, .3)])
    assert all(n.status == "correct" for n in result.notes)


def test_live_and_final_cutoff_agree():
    phrase = passage((0, 60), (.1, 62))
    attacks = [PlayedNote(62, .1, .2), PlayedNote(60, .12, .22)]
    early = live_assessment(phrase, "right", 60, [], from_beat=0,
        elapsed_seconds=.09, whole_take=True)
    assert not early.notes
    live = live_assessment(phrase, "right", 60, attacks, from_beat=0,
        elapsed_seconds=.12, whole_take=True)
    final = evaluate(phrase, "right", 60, attacks)
    assert [n.status for n in live.notes] == [n.status for n in final.notes]
    assert live.extra_notes == final.extra_notes == 1


def test_previous_attack_still_accepted_before_cutoff():
    phrase = passage((0, 60), (.1, 62))
    result = evaluate(phrase, "right", 60, [
        PlayedNote(60, .09, .11), PlayedNote(62, .1, .2)])
    assert all(n.status == "correct" for n in result.notes)
