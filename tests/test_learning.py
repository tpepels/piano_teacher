from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.learning import LearningPlan, build_exercises


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
    assert c.bpm == 48
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
