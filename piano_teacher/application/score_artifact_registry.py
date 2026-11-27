"""One artifact generation per exact physical score selection.

The musical session lock owns selection and the current pointer. Expensive
work never holds that lock and cannot mutate another generation.
"""
from __future__ import annotations

from .score_artifacts import ScoreArtifacts, ScoreSelection


class ScoreArtifactRegistry:
    def __init__(self, initial: ScoreArtifacts):
        self.current = initial
        self._selection_identity: tuple | None = None

    def select(self, selected: ScoreSelection) -> ScoreArtifacts:
        """Bind a generation while holding the musical session lock."""
        identity = selected.identity
        if self._selection_identity is not None and identity != self._selection_identity:
            self.invalidate()
        self._selection_identity = identity
        return self.current

    def adopt(self, prepared: ScoreArtifacts) -> None:
        if prepared is not self.current:
            self.current.retire()
            self.current = prepared
            self._selection_identity = None

    def invalidate(self) -> None:
        """Retire without waiting for either of the old generation's locks."""
        previous = self.current
        self.current = ScoreArtifacts(previous.preprocessing)
        self._selection_identity = None
        previous.retire()
