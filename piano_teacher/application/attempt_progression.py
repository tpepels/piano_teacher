"""Pure attempt timing decisions and source-measure grid caching.

The application owns MIDI, transport mutation, assessment, and persistence.
This policy receives explicit facts and callbacks for grading / tempo lookup;
it never receives PracticeEngine or any generic application object.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from typing import Any, Callable

from ..lesson_timing import lead_in_beats, preparation_meter
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
    preview: bool
    auto: bool
    mode: str
    coda: bool
    bpm: float
    gap_beats: float


@dataclass(frozen=True)
class AttemptStep:
    action: str
    next_boundary: float
    grid: tuple[float, ...]
    recovery: Any = None
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

    def schedule_start(self, *, phrase: Phrase,
                       boundaries: tuple[float, ...],
                       time_signatures: tuple,
                       bpm: float, position: float,
                       loop_continuation: bool, preview: bool,
                       now: float) -> AttemptStart:
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
        count_in = 0.0 if loop_continuation else lead_in_beats(bar_beats,bpm)
        return AttemptStart(
            from_beat=from_beat, count_in_bar_beats=bar_beats,
            count_in_meter=meter, count_in_beats=count_in,
            next_boundary_beat=next_chunk_end(grid,from_beat),
            run_at=now+count_in*60/bpm,
            next_action=("Watch the moving score; connect a piano for feedback."
                if preview else
                f"Play from bar {bar_number_at(grid,from_beat,phrase.first_bar)} at {bpm} BPM."))

    def inspect(self, tick: AttemptTick,
                recover: Callable[[float, tuple[float, ...]], Any],
                seconds_at: Callable[[float], float]) -> AttemptStep:
        """Decide the next transition without modifying transport or learner state."""
        grid = self.grid_for(tick.phrase,tick.boundaries)
        boundary = tick.next_boundary
        total_beats = tick.phrase.end-tick.phrase.start
        while (tick.mode == "practice" and tick.review_end is None
               and not tick.preview and (not tick.coda
                   or tick.score_beat >= total_beats - 1e-7)
               and boundary and tick.score_beat >= boundary):
            decision = recover(boundary,grid)
            if decision is not None:
                return AttemptStep("recovery",boundary,grid,recovery=decision)
            previous_boundary = boundary
            boundary = next_chunk_end(grid,previous_boundary)
            if boundary <= previous_boundary+1e-7:
                boundary = 0.0

        ending = (min(total_beats,tick.review_end)
                  if tick.review_end is not None else total_beats)
        duration = seconds_at(ending)-seconds_at(tick.from_beat)
        settlement = .20
        if tick.preview or (tick.auto and tick.review_end is None):
            settlement = min(settlement,tick.gap_beats*60/tick.bpm)
        if tick.now < tick.run_at+duration+settlement:
            return AttemptStep("waiting",boundary,grid)
        return AttemptStep("complete",boundary,grid,
                           ending=ending,duration=duration)
