"""Construct the lesson portion of a captured session snapshot.

The engine still owns lock ordering, transport reads and source selection;
this module only constructs the immutable lesson/tempo value objects.
"""
from __future__ import annotations

from .state_projection import LessonSnapshot, TempoSnapshot
from .measure_grid import phrase_grid
from .lesson_settings import SETTINGS


def build_lesson_snapshot(plan, exercise, variant, *, fingerprint: str,
                          warmup: bool, lesson_steps: tuple) -> LessonSnapshot:
    p = plan
    ex = exercise
    return LessonSnapshot(
        title=p.piece.title, kind=ex.kind,
        first_bar=ex.phrase.first_bar, last_bar=ex.phrase.last_bar,
        measure_boundaries=phrase_grid(p.active_phrase, p.piece.bar_boundaries),
        duration_beats=ex.phrase.end-ex.phrase.start,
        exercise_index=p.index, exercise_count=len(p.exercises),
        level=variant.level, level_number=p.variant_index+1,
        level_count=len(p.variants), required_notes=len(variant.notes),
        warmup=warmup, piece_last_bar=len(p.piece.bar_boundaries)-1,
        import_warnings=p.piece.import_warnings, hand=p.hand, hands=p.hands,
        lesson_steps=lesson_steps, lesson_step=p.lesson_step_number,
        lesson_steps_mastered=p.lesson_steps_mastered, mastered=tuple(p.mastered),
        fingerprint=fingerprint,
        tempo=TempoSnapshot(bpm=p.bpm, original_bpm=p.piece.bpm,
            target_bpm=p.target_bpm, start_bpm=p.start_bpm, streak=p.streak,
            rungs=p.tempo_rungs(), minimum_bpm=SETTINGS.minimum_bpm,
            maximum_bpm=SETTINGS.maximum_bpm,
            clean_runs_required=SETTINGS.clean_runs_to_master,
            manual_tempo_step_bpm=SETTINGS.manual_tempo_step_bpm,
            automatic_tempo_steps=SETTINGS.automatic_tempo_steps),
    )
