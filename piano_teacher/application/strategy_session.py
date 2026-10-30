"""Rebuild a learning plan after an independent strategy change.

This service coordinates source/stage compatibility with saved strategy
sessions. MIDI, transport, UI and persistence commits stay in PracticeEngine.
"""
from __future__ import annotations

from typing import Mapping, Protocol

from ..learning import LearningPlan


class StrategyProgress(Protocol):
    def has_strategy_session(self, fingerprint: str, profile: str) -> bool: ...
    def restore(self, plan: LearningPlan, fingerprint: str, *,
                restore_session: bool = True): ...


def restored_strategy_plan(
    previous: LearningPlan, *, settings: Mapping[str, str],
    progress: StrategyProgress, fingerprint: str, warmup: bool,
) -> LearningPlan:
    replacement = LearningPlan(
        previous.piece, warmup=warmup,
        exercise_strategy=settings["exercise_strategy"],
        timing_strategy=settings["timing_strategy"],
        tempo_strategy=settings["tempo_strategy"])
    replacement.target_bpm = previous.target_bpm
    has_saved = progress.has_strategy_session(fingerprint, replacement.profile)
    progress.restore(replacement, fingerprint, restore_session=has_saved)
    if has_saved:
        return replacement

    # On first selection, retain a nearby musical location but never copy
    # clean streak, mastery or an earned transformed-stage BPM.
    preferred = previous.active_variant.level
    if previous.exercise.kind == "learn":
        candidates = replacement._pipeline_stages(
            replacement.exercises[
                min(previous.index, len(replacement.exercises)-1)],
            previous.hand)
        experimental = sorted(
            (stage for stage in candidates if
             stage.shaped_tempo or stage.transformed_rhythm),
            key=lambda stage: (
                stage.shaped_tempo and stage.transformed_rhythm,
                stage.transformed_rhythm, stage.shaped_tempo),
            reverse=True)
        if experimental:
            preferred = experimental[0].variant.level
    replacement.restore_location(
        kind=previous.exercise.kind,
        first_bar=previous.exercise.phrase.first_bar,
        last_bar=previous.exercise.phrase.last_bar,
        hand=previous.hand, level=preferred)
    replacement.streak = 0
    replacement.bpm = replacement._tempo_for_current_stage()
    return replacement
