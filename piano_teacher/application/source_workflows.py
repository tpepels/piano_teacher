"""One application source-installation and fingering-correction workflow.

SourcePreparationSession serializes costly preparation; the application lock
covers only effects that install the validated source. No engine reference,
alternate source format or independent lesson-selection policy is used.
"""
from __future__ import annotations

from pathlib import Path
from ..learning import LearningPlan
from ..importing.pieces import import_piece


class SourceWorkflows:
    def __init__(self, *, lesson, notices, lifecycle,
                 recovery_streak, transport, source_preparation,
                 score_artifact_registry,
                 attempt, listen, preprocessing, fingering, progress,
                 fukuda_mistakes, library, library_health,
                 lock):
        self.lesson = lesson
        self.notices = notices
        self.lifecycle = lifecycle
        self.recovery_streak = recovery_streak
        self.transport = transport
        self.source_preparation = source_preparation
        self.score_artifact_registry = score_artifact_registry
        self.attempt = attempt
        self.listen = listen
        self.preprocessing = preprocessing
        self.fingering = fingering
        self.progress = progress
        self.fukuda_mistakes = fukuda_mistakes
        self.library = library
        self.library_health = library_health
        self.lock = lock

    def prepare(self, path: str, *, warmup: bool, diagnostics: bool):
        return self.source_preparation.prepare(
            Path(path).expanduser().resolve(), warmup=warmup,
            preprocessing=self.preprocessing, fingering=self.fingering,
            progress=self.progress, fukuda_mistakes=self.fukuda_mistakes,
            library=self.library, state_lock=self.lock,
            importer=import_piece, plan_type=LearningPlan,
            diagnostics=diagnostics)

    def install(self, prepared, *, warmup: bool) -> bool | None:
        """Called with application lock and source-mutation guard held."""
        self.transport.clear_take_end()
        self.lifecycle.stop(reason="source_changed")
        self.recovery_streak.clear()
        self.lesson.set_course_guided(False)
        self.lesson.install_source(
            plan=prepared.plan, source=str(prepared.path),
            fingerprint=prepared.fingerprint, warmup=warmup)
        self.lesson.select_opening(0.0)
        self.score_artifact_registry.invalidate()
        self.source_preparation.source_installed()
        self.transport.select_source()
        self.lesson.clear_guided_selection()
        self.notices.publish("Press Start to practice", "Press Start to practice.")
        self.lesson.advance_revision()
        self.attempt.reset_source_presentation()
        if self.lesson.flow_applies(self.lesson.plan, warmup=warmup):
            return prepared.resumed
        return None

    def _apply_listen_failure(self) -> None:
        failure = self.listen.take_failure()
        if failure is not None:
            self.transport.wait_for_player()
            self.notices.publish(failure, failure)

    def correction_identity(self, *, fingerprint: str | None = None):
        """Capture the exact original MIDI source before asynchronous work."""
        with self.lock:
            self._apply_listen_failure()
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

    def install_fingering_correction(self, corrected) -> None:
        """One source-bound state commit, under session and mutation guards."""
        selected = self.lesson.plan
        installed = self.source_preparation.correction_install(
            corrected, piece=selected.piece if selected is not None else None,
            fingerprint=self.lesson.fingerprint,
            score_revision=self.lesson.revision)
        self._apply_listen_failure()
        selected.piece = installed.piece
        self.score_artifact_registry.invalidate()
        self.lesson.publish_revision(installed.score_revision)
        if self.transport.source_revised(self.lesson.revision):
            self.listen.retarget_score(self.lesson.revision)

    def library_listing(self) -> dict:
        return self.library.scan()

    def library_health_status(self) -> dict:
        return self.library_health.snapshot()

    def start_library_health(self) -> dict:
        return self.library_health.start()

    def resolve_library(self, identifier: str):
        return self.library.resolve(identifier)

    def mark_library_opened(self, identifier: str, *, warmup: bool) -> None:
        if warmup:
            self.transport.select_source()
            self.lesson.set_course_guided(False)
            self.notices.publish(
                "Warm-up ready - left, right, then both hands",
                "Three clean passes unlock the next hand.")
            self.progress.save(self.lesson.plan, self.lesson.fingerprint)
        self.library.mark_opened(identifier)
