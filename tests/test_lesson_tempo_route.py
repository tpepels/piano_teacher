"""Editable committed lesson targets and mastery at focused measure tempo."""
import json
from dataclasses import replace

import pytest

from piano_teacher.lesson_settings import SETTINGS, load_lesson_settings
from piano_teacher.learning import LearningPlan, build_exercises
from piano_teacher.music import Note, Phrase, Piece


def make_piece(bars=8, bpm=110):
    boundaries = tuple(float(i * 4) for i in range(bars + 1))
    notes = tuple(Note(float(i * 4), float(i * 4 + 1), 60, 0, 0,
                       "right", f"attack-{i}") for i in range(bars))
    phrases = tuple(Phrase(i // 2 + 1, i + 1, min(i + 2, bars),
                           float(i*4),float(min(i+2,bars)*4),
                           tuple(n for n in notes
                                 if i*4 <= n.start < min(i+2,bars)*4))
                    for i in range(0,bars,2))
    return Piece("Repeated motive",bpm,notes,phrases,bar_boundaries=boundaries)


def test_focus_route_is_measured_in_source_bars_and_keeps_links():
    p = LearningPlan(make_piece(6))
    assert SETTINGS.focus_measures == 2
    assert [(e.kind,e.phrase.first_bar,e.phrase.last_bar)
            for e in p.exercises] == [
        ("learn",1,2),("learn",3,4),("connect",1,4),
        ("learn",5,6),("connect",3,6),("perform",1,6)]
    assert p.active_phrase.first_bar == 1
    assert p.active_phrase.last_bar == 2
    assert p.bpm == 44
    assert p.target_bpm == 110
    p.set_bpm(80)
    p.select(0)
    assert p.start_bpm == 32  # 40% of the *chosen target*, not MIDI source BPM


def test_manual_tempo_skips_rungs_not_clean_credit_and_is_bounded():
    p = LearningPlan(make_piece())
    identity = p.identity
    before = p.bpm
    assert p.increase_tempo() == before + SETTINGS.manual_tempo_step_bpm
    assert p.target_bpm == 110
    assert p.identity == identity
    assert p.streak == 0 and not p.mastered
    while p.bpm < p.target_bpm:
        p.increase_tempo()
    assert p.bpm == p.target_bpm
    assert p.increase_tempo() == p.target_bpm
    for i in range(SETTINGS.clean_runs_to_master - 1):
        assert "Clean pass" in p.apply_result(correct=2,total=2)
        assert p.identity == identity
    assert p.apply_result(correct=1,total=2).startswith("Repeat")
    assert p.streak == 0
    for i in range(SETTINGS.clean_runs_to_master):
        result = p.apply_result(correct=2,total=2)
    assert identity in p.mastered
    assert "next passage" in result
    assert p.exercise.phrase.first_bar == 3 and p.bpm == 44


def test_manual_tempo_does_not_reduce_target_or_promote_repeated_motive():
    p = LearningPlan(make_piece())
    p.increase_tempo()
    for _ in range(SETTINGS.clean_runs_to_master):
        p.apply_result(correct=2,total=2)
    # All bars contain exactly the same repeated motif, but their
    # source events are independently assessed before granting mastery.
    assert p.exercise.phrase.first_bar == 1
    # Target not yet reached, so there is no credit for clean slow takes.
    assert not p.mastered
    while p.bpm < p.target_bpm:
        p.increase_tempo()
    for _ in range(SETTINGS.clean_runs_to_master):
        p.apply_result(correct=2,total=2)
    assert p.exercise.phrase.first_bar == 3
    assert p.identity not in p.mastered


def test_versioned_json_settings_strict_validation(tmp_path):
    original = json.loads((__import__("pathlib").Path(__file__).parents[1] /
                           "piano_teacher/lesson_settings.json").read_text())
    settings = load_lesson_settings()
    assert settings.clean_runs_to_master >= 1
    assert settings.minimum_bpm <= settings.maximum_bpm
    for field,value in [
        ("start_tempo_fraction", 1.3),
        ("automatic_tempo_multiplier", 1.0),
        ("recovery_tempo_multiplier", 1.01),
        ("manual_tempo_step_bpm", 0),
        ("clean_runs_to_master", 0),
        ("focus_measures", 0),
        ("feedback_seconds", -1)]:
        invalid = {**original,field:value}
        path = tmp_path / "lesson.json"
        path.write_text(json.dumps(invalid))
        with pytest.raises(ValueError):
            load_lesson_settings(path)


def test_original_piece_performance_covers_sustained_ending_and_silent_bars():
    notes = (Note(2,3,60,0,0,"right","first"),
             Note(10,18,48,1,0,"left","sustained"))
    phrases = (Phrase(1,1,2,0,8,notes[:1]),
               Phrase(2,3,4,8,16,notes[1:]))
    piece = Piece("Full ending",80,notes,phrases,
                  bar_boundaries=(0,4,8,12,16,20))
    plan = LearningPlan(piece)
    assert plan.exercises[-1].kind == "perform"
    assert plan.exercises[-1].phrase.first_bar == 1
    assert plan.exercises[-1].phrase.last_bar == 5
    assert plan.exercises[-1].phrase.end == 20
    assert plan.exercises[-1].phrase.notes == notes


def test_manual_tempo_action_is_persisted_without_credit(tmp_path):
    from piano_teacher.server import PracticeEngine

    first = PracticeEngine(tmp_path, enable_midi=False)
    first.plan = LearningPlan(make_piece(4))
    first.fingerprint = "manual-tempo-progress"
    stage = first.plan.identity
    first.control("tempo_up")
    state = first.state()
    assert state["bpm"] == 44 + SETTINGS.manual_tempo_step_bpm
    assert state["target_bpm"] == 110
    assert state["manual_tempo_step_bpm"] == SETTINGS.manual_tempo_step_bpm
    assert not first.plan.mastered and first.plan.streak == 0
    first.db.close()

    second = PracticeEngine(tmp_path, enable_midi=False)
    try:
        second.plan = LearningPlan(make_piece(4))
        second.fingerprint = "manual-tempo-progress"
        second._restore()
        assert second.plan.identity == stage
        assert second.plan.bpm == state["bpm"]
        assert second.plan.target_bpm == 110
        assert second.plan.streak == 0
    finally:
        second.db.close()
