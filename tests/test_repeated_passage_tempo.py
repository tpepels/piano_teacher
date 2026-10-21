"""Exact repeated-passage tempo sharing never bypasses source-specific assessment."""
from dataclasses import replace

from piano_teacher.learning import LearningPlan
from piano_teacher.lesson_settings import SETTINGS
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.repeated_passages import exact_repetition_signature
from piano_teacher.server import PracticeEngine


def repeated_piece(*, altered_pitch=False, altered_duration=False, bars=None):
    pitches = (60, 62, 72, 74, 60, 62 + int(altered_pitch))
    notes = tuple(
        Note(i * 4.0, i * 4.0 + (2.0 if altered_duration and i == 5 else 1.0),
             pitch, 0, 0, "right", f"source-{i}") for i, pitch in enumerate(pitches)
    )
    boundaries = bars or tuple(float(i * 4) for i in range(7))
    phrases = tuple(Phrase(i // 2 + 1, i + 1, i + 2,
                           boundaries[i], boundaries[i+2],
                           tuple(n for n in notes if boundaries[i] <= n.start < boundaries[i+2]))
                    for i in (0, 2, 4))
    return Piece("Repeated motif", 110, notes, phrases,
                 bar_boundaries=boundaries)


def test_only_exact_identical_source_measures_share_bpm_and_not_mastery():
    p = LearningPlan(repeated_piece())
    first = p.identity
    p.increase_tempo()
    assert p.bpm == 44 + SETTINGS.manual_tempo_step_bpm
    p.select(1)
    assert p.bpm == 44  # Different musical notes receive no credit.
    p.select(3)
    assert p.exercise.phrase.first_bar == 5
    assert p.bpm == 44 + SETTINGS.manual_tempo_step_bpm
    assert p.identity != first and p.identity not in p.mastered and p.streak == 0
    # The previously learned source stage remains independent.
    p.select(0)
    assert p.bpm == 44 + SETTINGS.manual_tempo_step_bpm


def test_repeated_source_with_different_pitch_or_duration_is_not_equivalent():
    for variant in (repeated_piece(altered_pitch=True),
                    repeated_piece(altered_duration=True)):
        p = LearningPlan(variant)
        p.increase_tempo()
        p.select(3)
        assert p.bpm == p.start_bpm


def test_repetition_respects_source_bar_pattern_even_for_same_notes():
    piece = repeated_piece()
    first = piece.phrases[0]
    same_notes = tuple(replace(n, start=n.start + 16, end=n.end + 16)
                       for n in first.notes)
    repeated = Phrase(3, 5, 6, 16, 24, same_notes)
    assert exact_repetition_signature(piece,first,"right","original",minimum_attacks=2) == \
        exact_repetition_signature(piece,repeated,"right","original",minimum_attacks=2)
    assert exact_repetition_signature(piece,first,"right","original",minimum_attacks=3) is None
    assert exact_repetition_signature(piece,first,"left","original",minimum_attacks=2) != \
        exact_repetition_signature(piece,repeated,"right","original",minimum_attacks=2)
    changed_meter = replace(piece, bar_boundaries=(0,4,8,12,16,20,25))
    assert exact_repetition_signature(changed_meter,repeated,"right","original",minimum_attacks=2) != \
        exact_repetition_signature(piece,first,"right","original",minimum_attacks=2)


def test_local_error_slowdown_is_not_reset_by_equivalent_stage_history():
    p = LearningPlan(repeated_piece())
    p.increase_tempo()
    prior = p.bpm
    p.select(3)
    assert p.bpm == prior
    p.bpm = max(SETTINGS.minimum_bpm, round(p.bpm * SETTINGS.recovery_tempo_multiplier))
    recovered = p.bpm
    p.select(0)
    assert p.bpm == prior
    p.select(3)
    assert p.bpm == recovered
    assert not p.mastered


def test_repeated_tempo_inherits_across_saved_sessions(tmp_path):
    piece = repeated_piece()
    first = PracticeEngine(tmp_path,enable_midi=False)
    first.plan = LearningPlan(piece)
    first.fingerprint = "repeat-persistence"
    first.control("tempo_up")
    expected = first.plan.bpm
    first.db.close()
    second = PracticeEngine(tmp_path,enable_midi=False)
    try:
        second.plan = LearningPlan(piece)
        second.fingerprint = "repeat-persistence"
        second._restore()
        second.control("next")  # different source passage
        assert second.plan.bpm == second.plan.start_bpm
        second.control("next")  # connection performance is not equivalent
        assert second.plan.bpm == second.plan.start_bpm
        second.control("next")  # repeated source measures 5–6
        assert second.plan.bpm == expected
        assert second.plan.identity not in second.plan.mastered
        assert second.plan.streak == 0
    finally:
        second.db.close()


def test_target_change_invalidates_repeat_tempo_inheritance():
    p = LearningPlan(repeated_piece())
    p.increase_tempo()
    p.set_bpm(80)
    p.select(3)
    assert p.bpm == round(80 * SETTINGS.start_tempo_fraction)
    assert p.target_bpm == 80


def test_explicit_target_change_does_not_invent_transferable_tempo(tmp_path):
    piece = repeated_piece()
    first = PracticeEngine(tmp_path,enable_midi=False)
    first.plan = LearningPlan(piece)
    first.fingerprint = "no-inherited-settings"
    first.control("tempo",bpm=80)
    first.control("next")
    # A target selected in Settings is not evidence of playing at 80 BPM.
    assert first.plan.bpm == 32
    first.db.close()
    reopened = PracticeEngine(tmp_path,enable_midi=False)
    try:
        reopened.plan = LearningPlan(piece)
        reopened.fingerprint = "no-inherited-settings"
        reopened._restore()
        reopened.control("next")  # leave different measures for source 5-6
        reopened.control("next")
        assert reopened.plan.bpm == 32
        assert not reopened.plan.mastered
    finally:
        reopened.db.close()
