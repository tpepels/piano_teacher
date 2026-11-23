"""Opening a piece and correcting its fingering, in three owners.

SourcePreparationWorkflow does the costly import/fingering work outside
the application lock (under the source-mutation guard). SourceInstallation
installs a validated source or correction under the lock.
"""
from __future__ import annotations

from pathlib import Path
from ..learning import LearningPlan
from ..importing.pieces import import_piece


class SourcePreparationWorkflow:
    def __init__(self, *, lesson, source_preparation, preprocessing,
                 fingering, progress, listen_outcomes, lock):
        self.lesson = lesson
        self.source_preparation = source_preparation
        self.preprocessing = preprocessing
        self.fingering = fingering
        self.progress = progress
        self.listen_outcomes = listen_outcomes
        self.lock = lock

    def prepare(self, path: str, *, diagnostics: bool):
        return self.source_preparation.prepare(
            Path(path).expanduser().resolve(),
            preprocessing=self.preprocessing, fingering=self.fingering,
            progress=self.progress, state_lock=self.lock,
            importer=import_piece, plan_type=LearningPlan,
            diagnostics=diagnostics)

    def correction_identity(self, *, fingerprint: str | None = None):
        """Capture the exact original MIDI source before asynchronous work."""
        with self.lock:
            self.listen_outcomes.apply_failure()
            selected = self.lesson.plan
            return self.source_preparation.capture_correction(
                piece=selected.piece if selected is not None else None,
                fingerprint=self.lesson.fingerprint,
                requested_fingerprint=fingerprint)

    def prepare_fingering_correction(self, identity, *,
                                    source_id: str, finger: int | None):
        """Heavy correction while source_mutation is held; release state lock."""
        with self.lock:
            selected = self.lesson.plan
            piece = selected.piece if selected is not None else None
            fingerprint = self.lesson.fingerprint
        return self.source_preparation.correct_fingering(
            identity, piece=piece, fingerprint=fingerprint,
            source_id=source_id, finger=finger, fingering=self.fingering)


class SourceInstallation:
    def __init__(self, *, lesson, notices, lifecycle, plans,
                 transport, source_preparation, score, take, listen,
                 listen_outcomes):
        self.lesson = lesson
        self.notices = notices
        self.lifecycle = lifecycle
        self.plans = plans
        self.transport = transport
        self.source_preparation = source_preparation
        self.score = score
        self.take = take
        self.listen = listen
        self.listen_outcomes = listen_outcomes

    def install(self, prepared) -> bool | None:
        """Called with application lock and source-mutation guard held."""
        self.transport.clear_take_end()
        self.lifecycle.stop(reason="source_changed")
        self.plans.adopt(lambda: self.lesson.install_source(
            plan=prepared.plan, source=str(prepared.path),
            fingerprint=prepared.fingerprint))
        self.source_preparation.source_installed()
        self.notices.publish("Press Start to practice", "Press Start to practice.")
        self.take.reset_source_presentation()
        return prepared.resumed

    def install_fingering_correction(self, corrected) -> None:
        """One source-bound state commit, under session and mutation guards."""
        selected = self.lesson.plan
        installed = self.source_preparation.correction_install(
            corrected, piece=selected.piece if selected is not None else None,
            fingerprint=self.lesson.fingerprint,
            score_revision=self.lesson.revision)
        self.listen_outcomes.apply_failure()
        selected.piece = installed.piece
        self.score.invalidate_artifacts()
        self.lesson.publish_revision(installed.score_revision)
        if self.transport.source_revised(self.lesson.revision):
            self.listen.retarget_score(self.lesson.revision)
