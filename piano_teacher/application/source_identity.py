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

    def install(self, *, plan: LearningPlan, source: str, fingerprint: str) -> None:
        self.plan = plan
        self.source = source
        self.fingerprint = fingerprint

    def replace_plan(self, plan: LearningPlan | None) -> None:
        self.plan = plan

    def advance_revision(self) -> None:
        self.revision += 1

    def publish_revision(self, revision: int) -> None:
        self.revision = revision
