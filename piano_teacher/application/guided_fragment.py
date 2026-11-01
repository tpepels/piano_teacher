"""Source-measure selection for guided teaching, without engine mutation."""
from __future__ import annotations

import math
from dataclasses import dataclass

from ..measure_grid import phrase_grid
from ..music import Phrase


@dataclass(frozen=True)
class GuidedFragment:
    grid: tuple[float, ...]
    first_index: int
    end_index: int

    @property
    def start(self) -> float:
        return self.grid[self.first_index]

    @property
    def end(self) -> float:
        return self.grid[self.end_index]


def select_guided_fragment(phrase: Phrase,
                           boundaries: tuple[float, ...],
                           from_beat: float) -> GuidedFragment:
    grid = phrase_grid(phrase, boundaries)
    if not math.isfinite(from_beat) or not 0 <= from_beat < grid[-1]:
        raise ValueError("Choose a measure inside the active passage")
    first = max(i for i, beat in enumerate(grid[:-1])
                if beat <= from_beat + 1e-7)
    while first < len(grid)-1:
        end_index = min(first+2, len(grid)-1)
        if any(phrase.start+grid[first]-1e-7 <= note.start <
               phrase.start+grid[end_index]-1e-7
               for note in phrase.notes):
            return GuidedFragment(grid, first, end_index)
        first = end_index
    raise ValueError("No note attacks in the selected fragment")
