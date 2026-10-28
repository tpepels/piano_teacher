"""Assessment calculations are independent of PracticeEngine and its clocks."""
from piano_teacher.assessment_service import AssessmentService
from piano_teacher.music import Note, Phrase
from piano_teacher.practice import Assessment, NoteAssessment, PlayedNote


def source():
    one = Note(0, 1, 60, 0, 0, "right", "source-one")
    two = Note(4, 5, 64, 0, 0, "right", "source-two")
    return Phrase(1, 1, 2, 0, 8, (one, two)), one, two


def test_assess_take_scopes_grading_to_actual_source_notes():
    phrase, one, two = source()
    calls = []
    def grade(segment, hand, bpm, played):
        calls.append((segment, hand, bpm, played))
        return len(segment.notes)
    service = AssessmentService()
    assert service.assess_take(phrase, hand="right", bpm=80, played=[],
                               from_beat=0, end_beat=4, evaluator=grade) == 1
    assert calls[-1][0].notes == (one,)
    assert service.assess_take(phrase, hand="right", bpm=80, played=[],
                               from_beat=4, end_beat=8, evaluator=grade) == 1
    assert calls[-1][0].notes == (two,)
    assert calls[-1][0].start == 4


def test_review_reports_missed_wrong_and_unmatched_by_original_measure():
    phrase, one, two = source()
    result = Assessment(
        (NoteAssessment(one, "missed"), NoteAssessment(two, "wrong", played_pitch=65)),
        1, (PlayedNote(72, 3.0, None),))
    review = AssessmentService().review(phrase, result,
        bar_boundaries=(0, 4, 8), played_from_beat=0, bpm=80)
    assert review["total"] == 2 and review["correct"] == 0
    assert review["missed"] == 1 and review["wrong"] == 1
    assert review["extra_notes"] == 1
    assert review["missed_pitches"] == [60]
    assert [x["first_bar"] for x in review["sections"]] == [2, 1]
    assert review["sections"][0]["counts"]["wrong"] == 1
    assert review["sections"][0]["counts"]["extra"] == 1
    assert review["weakest_bars"][0]["start_beat"] == 4


def test_live_marks_do_not_invent_feedback_before_take_begins():
    phrase, _, _ = source()
    assert AssessmentService().live_marks(
        phrase=phrase, hand="right", bpm=80, played=[],
        played_from_beat=0, elapsed_seconds=-.1,
        bar_boundaries=(0, 4, 8), layout={}) == []
