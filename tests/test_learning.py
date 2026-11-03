from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.learning import LearningPlan, build_exercises
from piano_teacher.lesson_settings import SETTINGS


def make_piece(bars=6):
    notes = tuple(Note(float(i * 4), float(i * 4 + 1), 60+i, 0, 0, "right") for i in range(bars))
    phrases = tuple(Phrase(i // 2 + 1, i + 1, min(i + 2, bars), float(i*4), float(min(i+2,bars)*4),
                           tuple(n for n in notes if i*4 <= n.start < min(i+2,bars)*4))
                    for i in range(0,bars,2))
    return Piece('Sample', 120, notes, phrases)


def test_overlapping_connections_and_performance():
    p=make_piece(24)
    assert [(x.kind,x.phrase.first_bar,x.phrase.last_bar) for x in build_exercises(p)] == [
       ('learn',1,8), ('learn',9,16), ('connect',7,10),
       ('learn',17,24), ('connect',15,18), ('perform',1,24)]
    assert [(x.kind,x.phrase.first_bar,x.phrase.last_bar) for x in build_exercises(make_piece(6), consolidate=False)] == [
       ('learn',1,2), ('learn',3,4), ('connect',1,4),
       ('learn',5,6), ('connect',3,6), ('perform',1,6)]


def test_single_hand_piece_finishes_without_repeating_the_same_notes_as_both():
    c = LearningPlan(make_piece(2))
    assert c.hands == ('right',)
    assert c.bpm == SETTINGS.start_tempo_bpm
    assert 'Tempo increased' in c.apply_result(correct=2, total=2)
    while c.bpm < c.piece.bpm:
        c.apply_result(correct=2, total=2)
    assert c.streak == 0
    assert c.apply_result(correct=2, total=2) == 'Clean pass 1/3 - repeat'
    assert c.apply_result(correct=2, total=2) == 'Clean pass 2/3 - repeat'
    assert c.apply_result(correct=2, total=2) == 'Piece mastered'
    assert c.hand == 'right' and c.lesson_steps_mastered == 1


def test_failures_reset_streak_but_do_not_slow_without_five_errors():
    c = LearningPlan(make_piece(16))
    c.set_bpm(120)
    c.apply_result(correct=2,total=2)
    assert c.streak == 1
    c.apply_result(correct=1,total=2)
    assert c.streak == 0 and c.bpm == 120
    c.jump(2)
    assert c.exercise.kind == 'connect'
    assert c.hand == 'both'



def test_gapped_passages_are_not_joined():
    p=make_piece(6)
    p=Piece(p.title,p.bpm,p.notes,(p.phrases[0],p.phrases[2]))
    assert not any(x.kind == 'connect' for x in build_exercises(p))


def test_large_course_stage_index_preserves_step_numbers_and_mastery_across_navigation():
    from piano_teacher.learning import LearningPlan
    from piano_teacher.music import Note, Phrase, Piece
    notes = tuple(Note(float(i), float(i)+.5, 60+i%7, 0, 0, "right",
                       "source-"+str(i)) for i in range(48))
    piece = Piece("Steps", 90, notes, (
        Phrase(1,1,12,0,48,notes),),
        bar_boundaries=tuple(float(i) for i in range(0,49,4)))
    plan = LearningPlan(piece, exercise_strategy="source-progression")
    steps = plan.lesson_steps
    assert len(steps) > 6
    assert len(plan._lesson_step_numbers) == len(steps)
    for position in (1,3,len(steps)//2,len(steps)):
        plan.select_step(position)
        assert plan.lesson_step_number == position
        assert plan.lesson_steps is steps
    selected = {steps[0].key, steps[-1].key}
    plan.mastered = {key:90 for key in selected}
    plan.mastered["obsolete-previous-course"] = 90
    assert plan.lesson_steps_mastered == 2
    assert plan.lesson_step_number == len(steps)
