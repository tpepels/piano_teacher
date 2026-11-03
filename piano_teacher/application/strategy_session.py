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
    fukuda_mistakes: frozenset[str] | None = None,
    feedback: Mapping[str, str] | None = None,
) -> LearningPlan:
    replacement = LearningPlan(
        previous.piece, warmup=warmup,
        exercise_strategy=settings["exercise_strategy"],
        timing_strategy=settings["timing_strategy"],
        tempo_strategy=settings["tempo_strategy"],
        fukuda_mistakes=fukuda_mistakes, feedback=feedback)
    replacement.target_bpm = previous.target_bpm
    has_saved = progress.has_strategy_session(fingerprint, replacement.profile)
    progress.restore(replacement, fingerprint, restore_session=has_saved)
    if has_saved:
        return replacement

    # On first selection, keep the nearest *source measure*, not the
    # preceding generator's unrelated exercise index, hand catalog or level.
    # The new curriculum owns its order: begin at its first genuinely
    # selected stage for that source passage. Earlier code force-selected
    # the first rhythm/tempo experiment in a guessed exercise, bypassing
    # Fukuda's opening reduction and crashing if that exercise had no
    # matching hand. Explicitly saved sessions above still resume exactly.
    replacement.restore_location(
        kind=previous.exercise.kind,
        first_bar=previous.exercise.phrase.first_bar,
        last_bar=previous.exercise.phrase.last_bar,
        hand=previous.hand, level="")
    replacement.streak = 0
    replacement.bpm = replacement._tempo_for_current_stage()
    return replacement
