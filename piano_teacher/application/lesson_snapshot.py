"""Construct the lesson portion of a captured session snapshot.

The engine still owns lock ordering, transport reads and source selection;
this module only constructs the immutable lesson/tempo value objects.
"""
from __future__ import annotations

from ..state_projection import LessonSnapshot, TempoSnapshot
from ..measure_grid import phrase_grid
from ..lesson_settings import SETTINGS
from ..lesson_stage_semantics import describe


def build_lesson_snapshot(plan, exercise, variant, *, fingerprint: str,
                          warmup: bool, lesson_steps: tuple,
                          lesson_step_count: int = 0) -> LessonSnapshot:
    p = plan
    ex = exercise
    if p.generator_registration is not None and p.generator_registration.midi_only and not warmup:
        stage_info = describe(p.active_stage, p.stages[-1])
    else:
        stage_info = {"family": "Warm-up" if warmup else "Practice",
                      "label": "Source practice" if not warmup else "Warm-up practice",
                      "change": "source notes", "meaningful": False}
    return LessonSnapshot(
        title=p.piece.title, kind=ex.kind,
        first_bar=ex.phrase.first_bar, last_bar=ex.phrase.last_bar,
        measure_boundaries=phrase_grid(p.active_phrase, p.piece.bar_boundaries),
        duration_beats=ex.phrase.end-ex.phrase.start,
        exercise_index=p.index, exercise_count=len(p.exercises),
        level=variant.level,
        stage_family=stage_info["family"],
        stage_label=stage_info["label"],
        stage_change=stage_info["change"],
        stage_meaningful=stage_info["meaningful"],
        exercise_strategy=p.exercise_strategy.name,
        level_number=p.variant_index+1,
        level_count=len(p.variants), required_notes=len(variant.notes),
        warmup=warmup, piece_last_bar=len(p.piece.bar_boundaries)-1,
        import_warnings=p.piece.import_warnings, hand=p.hand, hands=p.hands,
        lesson_steps=lesson_steps, lesson_step_count=lesson_step_count,
        lesson_step=p.lesson_step_number,
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
