"""Count distinct MIDI attacks: amber is a warning, red is failure."""
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.practice import Assessment, NoteAssessment
from piano_teacher.instruction import next_full_attempt


def _note(onset, pitch=60):
    return Note(float(onset), float(onset)+.5, pitch, 0, 0, "right")


def _assessment(statuses, *, extra=0, notes=None):
    targets = notes or tuple(_note(i) for i in range(len(statuses)))
    return Assessment(tuple(NoteAssessment(note, status)
                            for note, status in zip(targets, statuses)), extra)


def test_one_warning_out_of_four_attacks_is_accepted():
    result = _assessment(("correct", "late", "correct", "correct"))
    assert result.yellow_attacks == 1
    assert result.total_attacks == 4
    assert result.passed and not result.clean
    assert result.summary.startswith("Accepted with warnings")


def test_exactly_half_yellow_attacks_retries():
    result = _assessment(("early", "late", "correct", "correct"))
    assert not result.passed
    assert result.yellow_attacks == 2


def test_chord_notes_share_one_attack_in_yellow_ratio():
    # Four printed heads on the same beat count as one attack.
    targets = (_note(0, 60), _note(0, 64), _note(0, 67),
               _note(1, 62), _note(2, 65), _note(3, 69))
    result = _assessment(("correct", "late", "correct",
                          "correct", "correct", "correct"), notes=targets)
    assert result.total_attacks == 4 and result.yellow_attacks == 1
    assert result.passed


def test_one_red_or_extra_attack_remains_failure():
    assert not _assessment(("correct","wrong","correct","correct")).passed
    assert not _assessment(("correct","missed","correct","correct")).passed
    assert not _assessment(("correct","correct","correct","correct"),extra=1).passed


def test_accepted_amber_advances_lesson_without_retry():
    targets = tuple(_note(i) for i in range(4))
    phrase = Phrase(1, 1, 1, 0, 4, targets)
    piece = Piece("Warnings", 100, targets, (phrase,),
                  bar_boundaries=(0, 4))
    plan = LearningPlan(piece, exercise_strategy="coda-part")
    result = _assessment(("correct", "late", "correct", "correct"), notes=targets)
    before = plan.bpm
    prompt = next_full_attempt(plan, result)
    assert "Retry" not in prompt
    message = plan.apply_result(correct=result.correct,total=len(result.notes),
                                extras=result.extra_notes,accepted=result.passed)
    assert "Repeat -" not in message
    assert plan.bpm >= before


def test_half_warning_attacks_break_streak_without_losing_warning_marks():
    targets = tuple(_note(i) for i in range(4))
    phrase = Phrase(1,1,1,0,4,targets)
    plan = LearningPlan(Piece("Warnings",100,targets,(phrase,),
                              bar_boundaries=(0,4)),exercise_strategy="coda-part")
    result = _assessment(("late","long","correct","correct"),notes=targets)
    assert not result.passed and not result.clean
    message = plan.apply_result(correct=result.correct,total=len(result.notes),
                                extras=0,accepted=result.passed)
    assert "Repeat" in message and plan.failures == 1
