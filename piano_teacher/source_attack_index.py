"""One original-order source attack index for all passage policies."""
from bisect import bisect_left
from .music import Piece

class SourceAttackIndex:
    """One source-order-preserving index for repeated passage range queries.

    The long Hanon score previously re-scanned every source note for each
    passage, seam and consolidation candidate. Sorting once by attack
    position bounds each query to the notes actually inside that passage.
    Returned tuples retain the original source note order and identities.
    """

    def __init__(self, piece: Piece):
        self._notes = piece.notes
        onsets = sorted((note.start, index)
                        for index, note in enumerate(piece.notes))
        self._starts = tuple(start for start, _ in onsets)
        self._indices = tuple(index for _, index in onsets)

    def notes_in(self, start: float, end: float) -> tuple:
        low = bisect_left(self._starts, start)
        high = bisect_left(self._starts, end)
        return tuple(self._notes[i] for i in sorted(self._indices[low:high]))
