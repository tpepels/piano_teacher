"""Current pre-engraved score artifact owner across stage promotion.

Promoting prepared future assets replaces this reference. Source invalidation,
history reset and all score readers therefore act on the current artifacts
rather than a previously captured generation.
"""
from __future__ import annotations
from .score_artifacts import ScoreArtifacts


class ScoreArtifactRegistry:
    def __init__(self, initial: ScoreArtifacts):
        self.current = initial

    def adopt(self, prepared: ScoreArtifacts) -> None:
        self.current = prepared

    def invalidate(self) -> None:
        self.current.invalidate()
