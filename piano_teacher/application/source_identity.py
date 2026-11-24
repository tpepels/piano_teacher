"""Installed MIDI source identity and published asset generation.

The learning plan owns curriculum state. This object holds the currently
installed immutable source identifier and the revision of its drawn assets.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..learning import LearningPlan


@dataclass(slots=True)
class SourceIdentity:
    plan: LearningPlan | None = None
    source: str | None = None
    fingerprint: str = ""
    revision: int = 0
    # What the published revision draws (recorded by the exposure install).
    drawn: tuple | None = None

    def install(self, *, plan: LearningPlan, source: str, fingerprint: str) -> None:
        self.plan = plan
        self.source = source
        self.fingerprint = fingerprint

    def replace_plan(self, plan: LearningPlan | None) -> None:
        self.plan = plan

    def advance_revision(self) -> None:
        self.revision += 1
        self.drawn = None

    def publish_revision(self, revision: int) -> None:
        # A newly published revision has not been described yet; the
        # exposure that published it records what it draws (record_drawn).
        self.revision = revision
        self.drawn = None

    def record_drawn(self, identity: tuple) -> None:
        """What the current revision draws (see Score.displayed_score)."""
        self.drawn = identity
