"""Focused MIDI-only tempo and grading contracts."""
import pytest

from piano_teacher.grading_tolerance import onset_tolerance
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.practice import PlayedNote, evaluate
from piano_teacher.live_input_view import LiveInputView
from piano_teacher.exercise_contracts import TempoMap, TempoSegment


def _piece(gap, *, bpm=100, count=8):
    notes = tuple(Note(i*gap, i*gap+gap*.9, 60+i%3, 0, 0,
                       "right", f"n{i}") for i in range(count))
    phrase = Phrase(1, 1, 2, 0, 8, notes)
    return Piece("Rhythm", bpm, notes, (phrase,), bar_boundaries=(0, 4, 8))


def test_sixteenths_and_32nds_start_slower_than_quarters():
    quarter = LearningPlan(_piece(1))
    sixteenth = LearningPlan(_piece(.25))
    thirty_second = LearningPlan(_piece(.125))
    assert (quarter.start_bpm, sixteenth.start_bpm, thirty_second.start_bpm) == (40, 30, 15)
    assert sixteenth.tempo_rungs()[0] == 30
    assert sixteenth.tempo_rungs()[-1] == 100


def test_isolated_rolled_onsets_do_not_slow_a_whole_passage():
    p = _piece(1)
    notes = (Note(0, .1, 60, 0, 0, "right", "rolled"),
             Note(.15, .25, 64, 0, 0, "right", "rolled-2"), *p.notes)
    phrase = Phrase(1, 1, 2, 0, 8, notes)
    piece = Piece("Roll", 100, notes, (phrase,), bar_boundaries=(0, 4, 8))
    assert LearningPlan(piece).start_bpm == 40


def test_per_stage_start_and_manual_tempo_survive_navigation():
    plan = LearningPlan(_piece(.25))
    step = next(i for i, s in enumerate(plan.lesson_steps, 1)
                if s.level == "original" and s.hand == "right")
    plan.select_step(step)
    assert plan.bpm == 30
    plan.decrease_tempo()
    assert plan.bpm == 25
    plan.select_step(1 if step != 1 else len(plan.lesson_steps))
    plan.select_step(step)
    assert plan.bpm == 25


def test_slow_practice_tolerates_drift_and_approximate_hold():
    phrase = Phrase(1, 1, 1, 0, 4, (Note(0, 1, 60, 0, 0, "right"),))
    assert onset_tolerance(1.5) == pytest.approx(.30)
    assert evaluate(phrase, "right", 40, [PlayedNote(60, .2, 1.1)]).clean
    assert evaluate(phrase, "right", 40, [PlayedNote(60, .4, 1.7)]).notes[0].status == "late"
    assert not evaluate(phrase, "right", 40, [PlayedNote(61, 0, 1)]).clean
    assert evaluate(phrase, "right", 120, [PlayedNote(60, .15, .65)]).notes[0].status == "late"


def test_repeated_note_uses_nearest_attack_not_the_first_unplayed_note():
    phrase = Phrase(1, 1, 1, 0, 2, (
        Note(0, .25, 60, 0, 0, "right", "first"),
        Note(.25, .50, 60, 0, 0, "right", "second")))
    result = evaluate(phrase, "right", 40, [PlayedNote(60, .375, .7)])
    assert [n.status for n in result.notes] == ["missed", "correct"]


def test_live_preview_and_final_grading_agree_at_slow_and_shaped_tempo():
    phrase = Phrase(1, 1, 1, 0, 4, (Note(0, 1, 60, 0, 0, "right", "s1"),))
    view = LiveInputView()
    for transport, bpm, tempo in [(1, 40, None), (2, 60, TempoMap("slow", (
            TempoSegment(0, 4, 40),)))]:
        view.reset_attempt()
        view.receive(pitch=60, is_on=True, now=10.2, phrase=phrase,
                     hand="right", bpm=bpm, from_beat=0, run_at=10,
                     running=True, paused=False, preview=False,
                     mode="practice", transport_id=transport, tempo_map=tempo)
        assert view.events[-1]["status"] == "on_time"
    assert evaluate(phrase, "right", 40, [PlayedNote(60, .2, 1.1)]).clean
