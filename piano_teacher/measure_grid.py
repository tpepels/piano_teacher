"""Measure-aware quarter-beat locations used for lesson notation and retries."""
from __future__ import annotations
from bisect import bisect_right
from .music import Phrase
from .lesson_settings import SETTINGS

def phrase_grid(phrase: Phrase, boundaries: tuple[float, ...] = ()) -> tuple[float, ...]:
    count = phrase.last_bar - phrase.first_bar + 1
    if count < 1 or phrase.end <= phrase.start:
        raise ValueError("The passage must contain at least one measure")
    if boundaries:
        start = phrase.first_bar - 1
        selected = boundaries[start:start + count + 1]
        if len(selected) != count + 1 or abs(selected[0] - phrase.start) > 0.0001 or abs(selected[-1] - phrase.end) > 0.0001:
            raise ValueError("Passage boundaries do not match the source MIDI measures")
        grid = tuple(round(value - phrase.start, 8) for value in selected)
    else:
        length = (phrase.end - phrase.start) / count
        grid = tuple(round(i * length, 8) for i in range(count)) + (round(phrase.end - phrase.start, 8),)
    if any(b <= a for a, b in zip(grid, grid[1:])):
        raise ValueError("Measure boundaries must be strictly increasing")
    return grid

def two_bar_chunks(grid: tuple[float, ...]) -> tuple[tuple[float, float], ...]:
    length = SETTINGS.focus_measures
    return tuple((grid[i], grid[min(i + length, len(grid) - 1)])
                 for i in range(0, len(grid) - 1, length))

def next_chunk_end(grid: tuple[float, ...], from_beat: float) -> float:
    return next((end for _, end in two_bar_chunks(grid) if end > from_beat + 1e-7), 0.0)

def chunk_start_at_end(grid: tuple[float, ...], end_beat: float) -> float:
    for start, end in two_bar_chunks(grid):
        if abs(end - end_beat) < 1e-6:
            return start
    raise ValueError("Requested boundary is not a two-measure boundary")

def bar_number_at(grid: tuple[float, ...], offset: float, first_bar: int) -> int:
    return first_bar + min(len(grid) - 2, max(0, bisect_right(grid, offset + 1e-7) - 1))
