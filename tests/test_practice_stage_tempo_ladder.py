"""Practice step navigation and the fixed-start, equally spaced tempo ladder."""
from __future__ import annotations

from piano_teacher.learning import LearningPlan
from piano_teacher.lesson_settings import SETTINGS
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.server import PracticeEngine


def song(bpm: int = 210, bars: int = 6) -> Piece:
    boundaries = tuple(float(i * 4) for i in range(bars + 1))
    notes = tuple(Note(i * 4.0, i * 4.0 + 1.0, 60 + i % 3, 0, 0,
                       "right", f"note-{i}") for i in range(bars))
    phrases = tuple(
        Phrase(i // 2 + 1, i + 1, min(i + 2, bars),
               boundaries[i], boundaries[min(i + 2, bars)],
               tuple(n for n in notes
                     if boundaries[i] <= n.start < boundaries[min(i + 2, bars)]))
        for i in range(0, bars, 2)
    )
    return Piece("Tempo ladder", bpm, notes, phrases, bar_boundaries=boundaries)


def test_every_song_uses_the_same_start_and_reaches_its_own_target():
    for bpm in (55, 110, 210):
        p = LearningPlan(song(bpm))
        assert p.start_bpm == SETTINGS.start_tempo_bpm
        assert p.bpm == SETTINGS.start_tempo_bpm
        assert p.tempo_rungs()[0] == SETTINGS.start_tempo_bpm
        assert p.tempo_rungs()[-1] == bpm
        assert len(p.tempo_rungs()) == SETTINGS.automatic_tempo_steps + 1
        gaps = [b - a for a, b in zip(p.tempo_rungs(), p.tempo_rungs()[1:])]
        assert max(gaps) - min(gaps) <= 1
        visited = [p.bpm]
        while p.bpm < p.target_bpm:
            p.apply_result(correct=2, total=2)
            assert p.bpm > visited[-1]
            visited.append(p.bpm)
        assert tuple(visited) == p.tempo_rungs()
        assert not p.mastered  # The step is only mastered at target BPM.


def test_slower_than_default_piece_does_not_start_above_target():
    p = LearningPlan(song(30))
    assert p.start_bpm == p.bpm == p.target_bpm == 30
    assert p.tempo_rungs() == (30,)


def test_manual_down_and_up_preserve_target_and_stage_identity():
    p = LearningPlan(song(110))
    first = p.identity
    assert p.decrease_tempo() == SETTINGS.start_tempo_bpm - SETTINGS.manual_tempo_step_bpm
    assert p.target_bpm == 110
    assert p.identity == first
    assert p.streak == 0 and not p.mastered
    assert p.increase_tempo() == SETTINGS.start_tempo_bpm
    for _ in range(50):
        p.decrease_tempo()
    assert p.bpm == SETTINGS.minimum_bpm
    assert p.decrease_tempo() == SETTINGS.minimum_bpm
    next_bpm = p.apply_result(correct=2, total=2)
    assert next_bpm.startswith("Tempo increased")
    assert SETTINGS.minimum_bpm < p.bpm <= SETTINGS.start_tempo_bpm


def test_any_step_can_be_selected_in_both_directions_with_own_tempo():
    p = LearningPlan(song(110))
    assert len(p.lesson_steps) >= 3
    first = p.identity
    p.decrease_tempo()
    slower = p.bpm
    p.select_step(len(p.lesson_steps))
    assert p.lesson_step_number == len(p.lesson_steps)
    assert p.identity != first
    assert p.bpm == SETTINGS.start_tempo_bpm
    assert not p.mastered
    p.select_step(1)
    assert p.identity == first
    assert p.bpm == slower
    assert p.streak == 0
    p.select_step(2)
    assert p.lesson_step_number == 2
    p.select_step(1)
    assert p.bpm == slower
    for invalid in (0, len(p.lesson_steps) + 1):
        try:
            p.select_step(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid lesson step should be rejected")


def test_server_controls_persist_step_choice_and_decrease(tmp_path):
    fingerprint = "exact-step-navigation"
    first = PracticeEngine(tmp_path, enable_midi=False)
    first.plan = LearningPlan(song(110))
    first.fingerprint = fingerprint
    first.control("tempo_down")
    assert first.state()["can_decrease_tempo"]
    stage_bpm = first.plan.bpm
    first.control("select_step", number=2)
    state = first.state()
    assert state["lesson_step"] == 2
    assert state["piece_fingerprint"] == fingerprint
    assert state["start_bpm"] == SETTINGS.start_tempo_bpm
    assert state["automatic_tempo_steps"] == SETTINGS.automatic_tempo_steps
    assert len(state["tempo_rungs"]) == SETTINGS.automatic_tempo_steps + 1
    assert first.lesson_overview()["piece_fingerprint"] == fingerprint
    assert not first.plan.mastered
    first.db.close()

    reopened = PracticeEngine(tmp_path, enable_midi=False)
    try:
        reopened.plan = LearningPlan(song(110))
        reopened.fingerprint = fingerprint
        reopened._restore()
        assert reopened.plan.lesson_step_number == 2
        reopened.control("select_step", number=1)
        assert reopened.plan.bpm == stage_bpm
        assert reopened.plan.streak == 0
    finally:
        reopened.db.close()
