"""Sparse practice passages should expand without turning connections into long drills."""
from dataclasses import replace

import pytest

from piano_teacher.learning import LearningPlan, build_exercises
from piano_teacher.lesson_settings import SETTINGS, load_lesson_settings
from piano_teacher.music import Note, Phrase, Piece


def piece_with_onsets(bars, onsets, *, boundaries=None):
    boundaries = tuple(float(i * 4) for i in range(bars + 1)) if boundaries is None else tuple(boundaries)
    notes = tuple(Note(float(beat), min(float(beat) + 1, boundaries[-1]),
                       60 + i % 12, 0, 0, "right", f"source-{i}")
                  for i, beat in enumerate(onsets))
    original = tuple(
        Phrase(i // 2 + 1, i + 1, min(i + 2, bars),
               boundaries[i], boundaries[min(i + 2, bars)],
               tuple(n for n in notes if boundaries[i] <= n.start < boundaries[min(i + 2, bars)]))
        for i in range(0, bars, 2)
    )
    return Piece("Sparse source", 100, notes, original, bar_boundaries=boundaries)


def ranges(exercises):
    return [(exercise.kind, exercise.phrase.first_bar, exercise.phrase.last_bar)
            for exercise in exercises]


def test_one_attack_every_two_bars_extends_focus_and_links_only_neighboring_measures():
    song = piece_with_onsets(12, range(0, 48, 8))
    exercises = build_exercises(song, consolidate=False)
    assert ranges(exercises) == [
        ("learn", 1, 4), ("learn", 5, 8), ("connect", 3, 6),
        ("learn", 9, 12), ("connect", 7, 10), ("perform", 1, 12),
    ]
    learned = [e for e in exercises if e.kind == "learn"]
    assert tuple(n.source_id for e in learned for n in e.phrase.notes) == tuple(n.source_id for n in song.notes)
    assert all(e.phrase.last_bar - e.phrase.first_bar + 1 <= SETTINGS.focus_max_measures
               for e in learned)


def test_dense_passages_still_use_two_measures_and_preserve_original_connections():
    song = piece_with_onsets(4, (0, 1, 4, 5, 8, 9, 12, 13))
    assert ranges(build_exercises(song, consolidate=False)) == [
        ("learn", 1, 2), ("learn", 3, 4), ("connect", 1, 4), ("perform", 1, 4)]


def test_chords_count_as_one_rhythmic_change_not_multiple_notes():
    song = piece_with_onsets(8, (0, 0, 0, 8, 16, 16, 16, 24))
    assert [r[1:] for r in ranges(build_exercises(song, consolidate=False)) if r[0] == "learn"] == [(1, 4), (5, 8)]
    # The original chord and source-note identities are unchanged.
    assert sum(len(e.phrase.notes) for e in build_exercises(song, consolidate=False) if e.kind == "learn") == 8


def test_all_silent_intermediate_bars_and_cap_are_preserved():
    song = piece_with_onsets(16, (0, 32))
    learned = [e for e in build_exercises(song, consolidate=False) if e.kind == "learn"]
    assert [(e.phrase.first_bar, e.phrase.last_bar) for e in learned] == [(1, 8), (9, 16)]
    assert learned[0].phrase.start == 0 and learned[0].phrase.end == 32
    assert learned[1].phrase.start == 32 and learned[1].phrase.end == 64


def test_short_sparse_tail_merges_backward_without_exceeding_cap():
    song = piece_with_onsets(5, (0, 8, 16))
    learned = [e for e in build_exercises(song, consolidate=False) if e.kind == "learn"]
    assert [(e.phrase.first_bar, e.phrase.last_bar) for e in learned] == [(1, 5)]
    assert learned[0].phrase.notes == song.notes


def test_source_meter_grid_is_used_for_variable_length_focus_passages():
    song = piece_with_onsets(6, (0, 11, 20), boundaries=(0, 3, 6, 11, 16, 20, 24))
    learned = [e for e in build_exercises(song, consolidate=False) if e.kind == "learn"]
    assert learned[0].phrase.first_bar == 1
    assert learned[0].phrase.end in song.bar_boundaries
    assert learned[-1].phrase.end in song.bar_boundaries
    assert sorted(n.source_id for e in learned for n in e.phrase.notes) == sorted(n.source_id for n in song.notes)


def test_historical_fixed_focus_can_be_reconstructed_for_saved_unversioned_sessions():
    song = piece_with_onsets(8, (0, 8, 16, 24))
    fixed = build_exercises(song, consolidate=False, adaptive_focus=False)
    assert [r[1:] for r in ranges(fixed) if r[0] == "learn"] == [(1, 2), (3, 4), (5, 6), (7, 8)]


def test_manual_five_bpm_controls_and_step_navigation_survive_sparse_grouping():
    plan = LearningPlan(piece_with_onsets(12, range(0, 48, 8)))
    first_step = plan.identity
    assert plan.exercise.phrase.last_bar == 4
    assert plan.decrease_tempo() == SETTINGS.start_tempo_bpm - SETTINGS.manual_tempo_step_bpm
    plan.select_step(len(plan.lesson_steps))
    plan.select_step(1)
    assert plan.identity == first_step
    assert plan.bpm == SETTINGS.start_tempo_bpm - SETTINGS.manual_tempo_step_bpm
    assert plan.increase_tempo() == SETTINGS.start_tempo_bpm
    assert not plan.mastered


@pytest.mark.parametrize("key,value", [
    ("focus_min_onsets", 0), ("focus_max_measures", 0), ("focus_max_measures", 1),
])
def test_sparse_focus_settings_reject_invalid_values(tmp_path, key, value):
    import json
    original = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    path = tmp_path / "lesson_settings.json"
    path.write_text(json.dumps({**original, key: value}))
    with pytest.raises(ValueError):
        load_lesson_settings(path)


from pathlib import Path
SETTINGS_PATH = Path(__file__).parents[1] / "piano_teacher" / "lesson_settings.json"
