"""Advance a timed practice attempt under PracticeEngine's existing lock.

Owns boundary inspection and completion scheduling, not MIDI, the musical
clock, grading policy, transport, or durable session state. A phrase's source
measure grid is immutable during its attempt and is built only once.
"""
from __future__ import annotations

from .practice_transitions import run_before_assessment
from ..lesson_settings import SETTINGS
from ..measure_grid import phrase_grid, next_chunk_end


class AttemptProgression:
    def __init__(self) -> None:
        self._phrase = None
        self._boundaries = None
        self._grid = None

    def grid_for(self, phrase, boundaries) -> tuple[float, ...]:
        if phrase is not self._phrase or boundaries is not self._boundaries:
            self._phrase = phrase
            self._boundaries = boundaries
            self._grid = phrase_grid(phrase, boundaries)
        return self._grid

    def advance(self, engine, now: float) -> None:
        """Inspect a single monotonic instant, stopping after the first transition."""
        if run_before_assessment(engine, now):
            return

        phrase = engine.plan.active_phrase
        total_beats = phrase.end - phrase.start
        score_beat = engine.play_from_beat + max(
            0.0, engine._elapsed_beat(now - engine.run_at))
        grid = self.grid_for(phrase, engine.plan.piece.bar_boundaries)

        # Coda practice may recover only at the end of its source phrase.
        # Other strategies inspect each completed authored source window.
        while (engine.mode == "practice" and engine.review_end_beat is None
               and not engine.preview_only
               and (engine.plan.exercise_strategy.name != "coda-part"
                    or score_beat >= total_beats - 1e-7)
               and engine.next_boundary_beat
               and score_beat >= engine.next_boundary_beat):
            tempo_map = engine._active_tempo_map()
            decision = engine.assessment_policies.select(tempo_map).recover(
                phrase, hand=engine.plan.hand, bpm=engine.plan.bpm,
                played=engine.recorder.presses if engine.recorder else [],
                from_beat=engine.play_from_beat,
                end_beat=engine.next_boundary_beat,
                grid=grid,
                threshold=(SETTINGS.warmup_recovery_errors
                           if engine.is_builtin_warmup
                           else SETTINGS.recovery_errors_in_window),
                warmup=engine.is_builtin_warmup, tempo=tempo_map)
            if decision is not None:
                engine._apply_rolling_recovery(
                    decision, phrase, grid, score_beat, now)
                return
            previous_boundary = engine.next_boundary_beat
            engine.next_boundary_beat = next_chunk_end(grid, previous_boundary)
            if engine.next_boundary_beat <= previous_boundary + 1e-7:
                engine.next_boundary_beat = 0.0

        ending = (min(total_beats, engine.review_end_beat)
                  if engine.review_end_beat is not None else total_beats)
        duration = (engine._elapsed_seconds(ending)
                    - engine._elapsed_seconds(engine.play_from_beat))
        # The settlement is inside the silent measure. It cannot postpone
        # the next attempt's absolute scheduled deadline.
        settlement = .20
        if engine.preview_only or (engine.auto and engine.review_end_beat is None):
            settlement = min(
                settlement, engine.visual_gap_beats * 60 / engine.plan.bpm)
        if now < engine.run_at + duration + settlement:
            return
        engine._complete_attempt(phrase, ending, total_beats, duration, now)
