"""Read-only source/score selection and on-demand native asset API.

All methods resolve the *current* artifact generation. Engraving and native
asset compilation take place after the brief selection snapshot, outside
the musical worker lock; no competing renderer or score source exists.
"""
from __future__ import annotations
from ..engraving.engraving import EngravedScore
from .score_artifacts import ScoreArtifacts, ScoreSelection


class ScoreReadServices:
    def __init__(self, *, lesson, take, lesson_execution,
                          score_artifact_registry, learner_progress, lock):
        self.lesson = lesson
        self.take = take
        self.lesson_execution = lesson_execution
        self.score_artifact_registry = score_artifact_registry
        self.learner_progress = learner_progress
        self.lock = lock

    def selection(self) -> ScoreSelection:
        plan = self.lesson.plan
        if plan is None:
            raise ValueError("No piece loaded")
        remediation = self.take.remediation_active
        return ScoreSelection(
            piece=plan.piece, phrase=self.lesson_execution.display_phrase(),
            hand=plan.hand, stage_key=plan.identity,
            revision=self.lesson.revision,
            fingerprint=self.lesson.fingerprint,
            transformed_rhythm=(remediation.transformed_rhythm
                if remediation is not None else plan.active_stage.transformed_rhythm),
            display_name=remediation.focus if remediation is not None else "")

    def source_model(self) -> dict:
        with self.lock:
            return self.score_artifact_registry.current.source_model(self.selection())

    def selected_artifacts(self) -> tuple[ScoreArtifacts, ScoreSelection]:
        with self.lock:
            return self.score_artifact_registry.current, self.selection()

    def semantic_score(self) -> dict:
        artifacts, selection = self.selected_artifacts()
        return artifacts.semantic_score(selection)

    def engraving(self) -> EngravedScore:
        artifacts, selection = self.selected_artifacts()
        return artifacts.engraving(selection)

    def geometry(self) -> dict:
        artifacts, selection = self.selected_artifacts()
        return artifacts.geometry(selection)

    def bundle(self) -> dict:
        """One snapshot and one compilation path for the active score."""
        artifacts, selection = self.selected_artifacts()
        return artifacts.bundle(selection)

    def completed_take_layout(self) -> dict:
        cached = self.score_artifact_registry.current.cached_layout(self.selection())
        if cached is None:
            raise RuntimeError(
                "Admitted score layout is unavailable for completed feedback")
        return cached.layout

    def guided_marks(self, snapshot: dict) -> list[dict]:
        if self.lesson.plan is None:
            return []
        engraving = self.score_artifact_registry.current.cached_layout(
            self.selection())
        return (self.lesson.guided_marks(snapshot, engraving.layout)
                if engraving is not None else [])

    def lesson_overview(self) -> dict:
        return self.learner_progress.lesson_overview(
            self.lesson.plan,
            fingerprint=self.lesson.fingerprint)
