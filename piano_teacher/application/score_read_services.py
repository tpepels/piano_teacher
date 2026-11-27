"""Read-only source/score selection and on-demand native asset API.

All methods resolve the *current* artifact generation. Engraving and native
asset compilation take place after the brief selection snapshot, outside
the musical worker lock; no competing renderer or score source exists.
"""
from __future__ import annotations
from ..engraving.engraving import EngravedScore
from .score_artifacts import ScoreArtifacts, ScoreSelection


class ScoreReadServices:
    def __init__(self, *, lesson, take, transport,
                          score_artifact_registry, learner_progress, lock):
        self.lesson = lesson
        self.take = take
        self.transport = transport
        self.score_artifact_registry = score_artifact_registry
        self.learner_progress = learner_progress
        self.lock = lock

    def selection(self) -> ScoreSelection:
        plan = self.lesson.plan
        if plan is None:
            raise ValueError("No piece loaded")
        remediation = self.lesson.flow_aid
        return ScoreSelection(
            piece=plan.piece, phrase=self.lesson.display_phrase(learning=self.transport.mode == "learn"),
            hand=plan.hand, stage_key=plan.identity,
            revision=self.lesson.revision,
            fingerprint=self.lesson.fingerprint,
            transformed_rhythm=(remediation.transformed_rhythm
                if remediation is not None else plan.active_stage.transformed_rhythm),
            display_name=remediation.focus if remediation is not None else "")

    def displayed_score(self, *, learning: bool | None = None, aid=...) -> tuple:
        """What the drawn score depends on (not its revision number):
        piece, window phrase, hand, stage and any aid. Equal values mean
        the notes on screen would be identical."""
        plan = self.lesson.plan
        if plan is None:
            return ()
        if learning is None:
            learning = self.transport.mode == "learn"
        if aid is ...:
            aid = self.lesson.flow_aid if learning else None
        phrase = self.lesson.display_phrase(learning=learning)
        return (self.lesson.fingerprint, plan.identity, plan.hand,
                aid.focus if aid is not None else None,
                aid.transformed_rhythm if aid is not None else plan.active_stage.transformed_rhythm,
                phrase.first_bar, phrase.last_bar, phrase.start, phrase.end,
                tuple((n.source_id, n.start, n.end, n.pitch) for n in phrase.notes))

    def source_model(self) -> dict:
        with self.lock:
            selected = self.selection()
            artifacts = self.score_artifact_registry.select(selected)
            return artifacts.source_model(selected)

    def selected_artifacts(self) -> tuple[ScoreArtifacts, ScoreSelection]:
        with self.lock:
            selected = self.selection()
            return self.score_artifact_registry.select(selected), selected

    def semantic_score(self) -> dict:
        artifacts, selection = self.selected_artifacts()
        return artifacts.semantic_score(selection)

    def engraving(self) -> EngravedScore:
        artifacts, selection = self.selected_artifacts()
        return artifacts.engraving(selection)

    def geometry(self) -> dict:
        artifacts, selection = self.selected_artifacts()
        return artifacts.geometry(selection)

    def bundle(self, expected: dict | None = None) -> dict:
        """Compile an exact selection; never substitute a later source."""
        artifacts, selection = self.selected_artifacts()
        identity = {
            "fingerprint": selection.fingerprint,
            "revision": selection.revision,
            "stage_key": selection.stage_key,
            "hand": selection.hand,
        }
        if expected is not None and expected != identity:
            raise ValueError("Score request was superseded before preparation")
        result = artifacts.bundle(selection)
        # Only the short selection check takes the session lock. A retired
        # artifact may populate its own cache but cannot publish live ink.
        with self.lock:
            if self.score_artifact_registry.current is not artifacts:
                raise ValueError("Score request was superseded during preparation")
            if self.selection().identity != selection.identity:
                raise ValueError("Score request was superseded during preparation")
        return result

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
