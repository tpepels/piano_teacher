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


def test_absolute_late_deadline_with_sparse_notes_and_slow_tempo():
    phrase = passage((0, 60), (2, 62))
    attacks = [PlayedNote(60, .21, .4)]
    result = evaluate(phrase, "right", 30, attacks)
    assert result.notes[0].status == "missed"
    assert result.extra_notes == 1
    live = live_assessment(phrase, "right", 30, attacks, from_beat=0,
        elapsed_seconds=.21, whole_take=True)
    assert live.notes[0].status == "missed"
    assert live.extra_notes == 1


def test_late_limit_is_exclusive_and_preserves_early_window():
    phrase = passage((0, 60))
    assert evaluate(phrase, "right", 30, [PlayedNote(60, .19, .4)]).notes[0].status == "correct"
    assert evaluate(phrase, "right", 30, [PlayedNote(60, .20, .4)]).notes[0].status == "missed"
    assert evaluate(phrase, "right", 30, [PlayedNote(60, -.3, .1)]).notes[0].status == "correct"


def test_accuracy_threshold_keeps_existing_failure_conditions():
    from piano_teacher.application.assessment_verdict import AssessmentVerdict
    from piano_teacher.lesson_settings import SETTINGS
    phrase = passage((0, 60))
    def verdict(onset, pitch=60):
        result = evaluate(phrase, "right", 60, [PlayedNote(pitch, onset, .2)])
        return AssessmentVerdict.decide(result, policy="practice-flow", eligible=True)
    assert SETTINGS.minimum_accuracy_percent == 85.0
    assert verdict(.025).accepted
    assert not verdict(.05).accepted
    assert not verdict(0, 61).accepted
