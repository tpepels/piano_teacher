"""Advance a timed practice attempt under PracticeEngine's existing lock.

Owns boundary inspection and completion scheduling, not MIDI, the musical
clock, grading policy, transport, or durable session state. A phrase's source
measure grid is immutable during its attempt and is built only once.
"""
from __future__ import annotations
import time

from ..practice import Recorder
from ..lesson_timing import lead_in_beats, preparation_meter

from .practice_transitions import run_before_assessment
from ..lesson_settings import SETTINGS
from ..measure_grid import phrase_grid, next_chunk_end, bar_number_at


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

    def begin(self, engine, *, from_beat: float | None,
              mode: str, loop_continuation: bool) -> None:
        engine.mode = mode
        engine.teaching = None
        engine.guided_range = None
        engine._guided_return = None
        engine.performance_summary = None
        engine.review_stage_identity = None
        engine.review_session_complete = False
        # A user must be able to watch the time-driven score without a
        # connected instrument. Only actual MIDI input enables assessment.
        engine.preview_only = not engine.midi.connected
        phrase=engine.plan.active_phrase
        position = engine.open_from_beat if from_beat is None else from_beat
        engine.play_from_beat=max(0.0,min(float(position),phrase.end-phrase.start-1e-6))

        engine.visual_transport.begin_take(loop_continuation=loop_continuation)
        engine.transport_id+=1
        engine.live_input.reset_attempt()
        # Keep large-score attack indexing off the physical MIDI callback.
        engine.live_input.prepare(phrase)
        engine.running=True
        engine.auto=mode == "practice" and not engine.preview_only
        engine.awaiting_score_revision=None
        engine.pending_result=None
        engine.feedback_marks=[]
        engine.feedback_unmapped=0
        engine.recorder=Recorder()
        grid=engine.attempt_progression.grid_for(
            phrase,engine.plan.piece.bar_boundaries)
        active_bar = max(0, min(len(grid)-2,
            next((i for i in range(len(grid)-1) if grid[i] <= engine.play_from_beat < grid[i+1]), len(grid)-2)))
        engine.count_in_bar_beats = grid[active_bar + 1] - grid[active_bar]
        engine.count_in_meter = [max(1, round(engine.count_in_bar_beats)), 4]
        source_beat = phrase.start + engine.play_from_beat
        meter = next(((numerator, denominator) for beat, numerator, denominator
                      in sorted(engine.plan.piece.time_signatures, reverse=True)
                      if beat <= source_beat + 1e-7), None)
        meter = preparation_meter(
            meter, engine.plan.piece.time_signatures, source_beat)
        if meter is not None:
            engine.count_in_meter = list(meter)
            engine.count_in_bar_beats = meter[0] * 4 / meter[1]
        # The empty staff measure BETWEEN loops already provides the
        # preparation interval. Do not prepend another count-in measure.
        engine.visual_gap_beats = engine._source_model()["practice_timeline"]["gap"]["duration_beats"]
        engine.count_in_beats = (0.0 if loop_continuation else
            lead_in_beats(engine.count_in_bar_beats, engine.plan.bpm))
        engine.next_boundary_beat=next_chunk_end(grid,engine.play_from_beat)
        engine.run_at=time.monotonic()+engine.count_in_beats*60/engine.plan.bpm
        engine.feedback="Count in, then play"
        engine.next_action = ("Watch the moving score; connect a piano for feedback." if engine.preview_only
            else f"Play from bar {bar_number_at(grid,engine.play_from_beat,phrase.first_bar)} at {engine.plan.bpm} BPM.")

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
