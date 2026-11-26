from piano_teacher.application.attack_admission import accepts_attack
from piano_teacher.music import Note, Phrase
from piano_teacher.exercise_contracts import TempoMap, TempoSegment


def admitted(seconds, *, notes=(0, 1, 4, 5), hand="right", tempo=None):
    phrase = Phrase(1, 1, 2, 0, 8,
        tuple(Note(beat, beat+2, 60, 0, 0, "right") for beat in notes))
    return accepts_attack(phrase, hand=hand, boundaries=(0, 4, 8),
        bpm=60, tempo=tempo, from_beat=0, elapsed=seconds)


def test_first_attack_can_be_early():
    assert admitted(-0.2)
    assert not admitted(-1.0)


def test_trailing_rest_does_not_register_new_attacks():
    assert admitted(1.5)  # late within original matching window
    assert not admitted(2.0)  # held note or trailing silence
    assert admitted(3.8)  # early first attack of next measure
    assert admitted(4.0)
    assert not admitted(6.0)


def test_inner_gap_is_still_graded():
    assert admitted(2.0, notes=(0, 3, 4))


def test_measure_tail_uses_authored_tempo():
    tempo = TempoMap("test", (TempoSegment(0, 4, 120), TempoSegment(4, 8, 60)))
    assert admitted(0.75, tempo=tempo)
    assert not admitted(1.2, tempo=tempo)
    assert admitted(1.9, tempo=tempo)


def test_late_last_attack_can_cross_barline_into_empty_measure():
    assert admitted(4.1, notes=(0, 3.75))
    assert not admitted(4.5, notes=(0, 3.75))
