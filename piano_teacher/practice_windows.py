"""One source-bound authority for routine practice windows.

A new measure is learned on its own before joining increasingly many
preceding measures, ending at a maximum width of four authored bars.
The distinct final whole-piece examination is not a practice window.

Window boundaries are in original MIDI quarter-beats; notes keep their
original source IDs and full key-release times. An attack belongs to the
window containing its onset. A release extending past the final barline
remains in the window, but does not add another *authored* bar.
"""
from __future__ import annotations

from dataclasses import dataclass

from .adaptive_hybrid_curriculum import _SourceAttackIndex
from .music import Piece, Phrase

MAX_PRACTICE_BARS = 4


@dataclass(frozen=True, slots=True)
class PracticeWindow:
    first_bar: int
    last_bar: int
    first_beat: float
    last_beat: float
    notes: tuple
    source_end: float
    window_key: str
    introduced_bar: int

    @property
    def width(self) -> int:
        return self.last_bar - self.first_bar + 1

    @property
    def is_new_measure(self) -> bool:
        return self.width == 1

    def phrase(self, number: int) -> Phrase:
        return Phrase(number, self.first_bar, self.last_bar,
                      self.first_beat, self.last_beat, self.notes)


def moving_windows(piece: Piece, *, maximum_bars: int = MAX_PRACTICE_BARS
                   ) -> tuple[PracticeWindow, ...]:
    """Build n, n-1..n, ... max 4 bars, then advance to n+1.

    Zero-attack windows are omitted. A measure with no attacks will still
    be represented when attached to a neighbouring sounding measure,
    preserving its genuine source rest rather than inventing a keypress.
    The optional cap is limited by the production contract.
    """
    if type(maximum_bars) is not int or not 1 <= maximum_bars <= 4:
        raise ValueError("A routine practice window must have 1-4 bars")
    grid = piece.bar_boundaries
    if len(grid) < 2:
        raise ValueError("Imported score has no authored bar boundaries")
    source = _SourceAttackIndex(piece)
    windows: list[PracticeWindow] = []
    for last in range(1, len(grid)):
        for width in range(1, min(maximum_bars, last) + 1):
            first = last - width + 1
            start, bar_end = grid[first - 1], grid[last]
            attacks = source.notes_in(start - 1e-7, bar_end - 1e-7)
            if not attacks:
                continue
            sounding_end = max(bar_end, *(note.end for note in attacks))
            windows.append(PracticeWindow(
                first_bar=first, last_bar=last,
                first_beat=start, last_beat=bar_end,
                notes=attacks, source_end=sounding_end,
                window_key=f"flow:window:{first}-{last}",
                introduced_bar=last))
    if not windows:
        raise ValueError("No playable source attacks in the piece")
    return tuple(windows)
