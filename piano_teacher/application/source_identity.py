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
    warmup: bool = False
    revision: int = 0
    _prepared_exposure: tuple[str, str, object] | None = None

    def install(self, *, plan: LearningPlan, source: str, fingerprint: str,
                warmup: bool) -> None:
        self.plan = plan
        self.source = source
        self.fingerprint = fingerprint
        self.warmup = warmup
        self._prepared_exposure = None

    def replace_plan(self, plan: LearningPlan | None) -> None:
        self.plan = plan
        self._prepared_exposure = None

    def advance_revision(self) -> None:
        self.revision += 1

    def publish_revision(self, revision: int) -> None:
        self.revision = revision

    def prepare_exposure(self, exposure) -> None:
        """Keep the selected exposure tied to this score's source and stage.

        A source change invalidates it. A revision change for the same
        engraving does not: score_ready must retain the approved lesson
        selection while native preparation runs.
        """
        if exposure is None:
            self._prepared_exposure = None
            return
        if self.plan is None or exposure.stage_key != self.plan.identity:
            raise ValueError("Prepared exposure does not match the selected lesson")
        self._prepared_exposure = (self.fingerprint, self.plan.identity, exposure)

    def selected_exposure(self):
        selection = self._prepared_exposure
        if selection is None or self.plan is None:
            return None
        fingerprint, stage_key, exposure = selection
        if fingerprint != self.fingerprint or stage_key != self.plan.identity:
            return None
        return exposure
