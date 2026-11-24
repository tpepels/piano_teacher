"""Pure attempt timing decisions and source-measure grid caching.

The application owns MIDI, transport mutation, assessment, and persistence.
This policy receives explicit facts and callbacks for grading / tempo lookup;
it never receives PracticeEngine or any generic application object.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from typing import Any, Callable

from ..lesson_timing import preparation_meter
from .musical_scheduler import SCHEDULER, SETTLEMENT_SECONDS
from .playback_transitions import CountInPlan
from .playback_facts import (
    FullPassageFacts, PassageRuntimeFacts, PassageFinishPlan,
)
from .passage_outcome_presenter import next_action as passage_next_action

from ..measure_grid import phrase_grid, next_chunk_end, bar_number_at
from ..music import Phrase


@dataclass(frozen=True)
class AttemptStart:
    from_beat: float
    count_in_bar_beats: float
    count_in_meter: tuple[int, int]
    count_in_beats: float
    next_boundary_beat: float
    run_at: float
    next_action: str


@dataclass(frozen=True)
class AttemptTick:
    phrase: Phrase
    boundaries: tuple[float, ...]
    now: float
    score_beat: float
    from_beat: float
    run_at: float
    next_boundary: float
    review_end: float | None
    auto: bool
    mode: str
    bpm: float
    gap_beats: float


@dataclass(frozen=True)
class AttemptStep:
    action: str
    next_boundary: float
    grid: tuple[float, ...]
    ending: float = 0.0
    duration: float = 0.0


class AttemptProgression:
    def __init__(self) -> None:
        self._phrase = None
        self._boundaries = None
        self._grid = None

    def grid_for(self, phrase: Phrase,
                 boundaries: tuple[float, ...]) -> tuple[float, ...]:
        if phrase is not self._phrase or boundaries is not self._boundaries:
            self._phrase = phrase
            self._boundaries = boundaries
            self._grid = phrase_grid(phrase, boundaries)
        return self._grid

    def count_in_bar(self, *, phrase: Phrase,
                     boundaries: tuple[float, ...], time_signatures: tuple,
                     position: float) -> tuple[float, float, tuple[int, int]]:
        """Return (from_beat, bar_beats, meter) of the bar a take starts in."""
        from_beat = max(0.0, min(float(position),
                                 phrase.end - phrase.start - 1e-6))
        grid = self.grid_for(phrase, boundaries)
        active_bar = max(0, min(len(grid) - 2,
                                bisect_right(grid, from_beat) - 1))
        bar_beats = grid[active_bar + 1] - grid[active_bar]
        meter = (max(1, round(bar_beats)), 4)
        source_beat = phrase.start + from_beat
        authored_meter = next(
            ((numerator, denominator)
             for beat, numerator, denominator
             in sorted(time_signatures, reverse=True)
             if beat <= source_beat + 1e-7), None)
        authored_meter = preparation_meter(
            authored_meter, time_signatures, source_beat)
        if authored_meter is not None:
            meter = tuple(authored_meter)
            bar_beats = meter[0] * 4 / meter[1]
        return from_beat, bar_beats, meter

    def next_count_in(self, *, phrase: Phrase | None, boundaries: tuple[float,...],
                      time_signatures: tuple, bpm: float, start_from: float,
                      already_active: bool, current_bar_beats: float,
                      current_meter: tuple[int,int]) -> tuple[float, tuple[int,int]]:
        """Return one count-in time AND meter from the same authored bar.

        The backend and the graphical CountInPlan continue to use one
        musical scheduling policy. A paused take reuses its original bar
        rather than reselecting a meter from a later measure.
        """
        meter = tuple(current_meter)
        if phrase is None or bpm <= 0.0:
            return 0.0,meter
        bar_beats = current_bar_beats
        if not already_active:
            _,bar_beats,meter = self.count_in_bar(
                phrase=phrase,boundaries=boundaries,
                time_signatures=time_signatures,position=start_from)
        return ((SCHEDULER.count_in_beats(bar_beats,bpm)
                 if bar_beats > 0 else 0.0),meter)

    def schedule_start(self, *, phrase: Phrase,
                       boundaries: tuple[float, ...],
                       time_signatures: tuple,
                       bpm: float, position: float,
                       loop_continuation: bool,
                       now: float, count_in_plan: CountInPlan | None = None
                       ) -> AttemptStart:
        from_beat, bar_beats, meter = self.count_in_bar(
            phrase=phrase, boundaries=boundaries,
            time_signatures=time_signatures, position=position)
        grid = self.grid_for(phrase, boundaries)
        if count_in_plan is not None:
            if (count_in_plan.meter != tuple(meter)
                    or abs(count_in_plan.bar_beats-bar_beats) > 1e-6
                    or abs(count_in_plan.bpm-bpm) > 1e-6):
                raise ValueError("Attempt and authorized count-in disagree")
            count_in = count_in_plan.beats
        else:
            raise ValueError("A timed take requires its authorized count-in plan")
        return AttemptStart(
            from_beat=from_beat, count_in_bar_beats=bar_beats,
            count_in_meter=meter, count_in_beats=count_in,
            next_boundary_beat=next_chunk_end(grid,from_beat),
            run_at=SCHEDULER.initial(now=now,bpm=bpm,
                count_in_beats=count_in).run_at,
            next_action=f"Play from bar {bar_number_at(grid,from_beat,phrase.first_bar)} at {bpm} BPM.")

    @staticmethod
    def plan_full_passage(facts: FullPassageFacts,
                          runtime: PassageRuntimeFacts) -> PassageFinishPlan:
        """Project a selected result into one metrical playback publication.

        An automatic take repeated at the same step (same window, timed)
        follows after the printed one-bar rest. Free, the next hand/window
        and piece completion are selected immediately; messages never add
        a pedagogical waiting interval.
        """
        pending,decision = facts.pending,facts.pending.decision
        exposure = decision.next_exposure
        same_timed = (exposure is not None and exposure.stage_key == facts.stage_key
            and exposure.mode == "practice" and decision.remediation is None)
        notice = passage_next_action(pending,target_bpm=facts.target_bpm,
            start_beat=runtime.from_beat,assessed_bpm=facts.assessed_bpm)
        if not runtime.automatic:
            return PassageFinishPlan("stop",next_action=notice)
        if not same_timed:
            return PassageFinishPlan("ready",next_action=notice)
        from ..notation.practice_timeline import retry_preparation_rest_beats
        bar = retry_preparation_rest_beats(facts.source_model,exposure.from_beat)
        # This printed rest is a continuation of the OUTGOING immutable
        # source and runs at that source's tempo. The incoming faster BPM
        # would shorten it, placing the next first header into still-visible
        # old rest ink. The incoming tempo begins at the authorized downbeat.
        deadline = SCHEDULER.repeat(run_at=runtime.run_at,
            source_seconds=facts.duration,gap_beats=bar,bpm=facts.bpm)
        return PassageFinishPlan("announce",deadline=deadline,next_action=notice)

    @staticmethod
    def preloaded_feedback_due(source, *, now: float, run_at: float,
                               from_beat: float) -> bool:
        finish = (run_at+SCHEDULER.source_seconds(source.tempo,source.duration_beats,source.bpm)
            - SCHEDULER.source_seconds(source.tempo,from_beat,source.bpm)+SETTLEMENT_SECONDS)
        return now >= finish-1e-7

    def inspect(self, tick: AttemptTick,
                checkpoint: Callable[[float], None],
                seconds_at: Callable[[float], float]) -> AttemptStep:
        """Decide the next transition without modifying transport or learner state."""
        grid = self.grid_for(tick.phrase,tick.boundaries)
        boundary = tick.next_boundary
        total_beats = tick.phrase.sounding_end-tick.phrase.start
        while (tick.mode == "practice" and tick.review_end is None
               and boundary and tick.score_beat >= boundary):
            # Persist the played prefix at each bar (evidence durability).
            checkpoint(boundary)
            previous_boundary = boundary
            boundary = next_chunk_end(grid,previous_boundary)
            if boundary <= previous_boundary+1e-7:
                boundary = 0.0

        ending = (min(total_beats,tick.review_end)
                  if tick.review_end is not None else total_beats)
        duration = seconds_at(ending)-seconds_at(tick.from_beat)
        if tick.now < tick.run_at+duration:
            return AttemptStep("waiting",boundary,grid)
        return AttemptStep("complete",boundary,grid,
                           ending=ending,duration=duration)
