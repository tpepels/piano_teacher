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
    def __init__(self, *, source_identity, lesson_cursor, notices, lifecycle,
                 recovery_streak, visual_transport, source_preparation,
                 playback_session, guided_session, score_artifact_registry,
                 attempt, listen, preprocessing, fingering, progress,
                 fukuda_mistakes, library, library_health, flow_session,
                 lock):
        self.source_identity = source_identity
        self.lesson_cursor = lesson_cursor
        self.notices = notices
        self.lifecycle = lifecycle
        self.recovery_streak = recovery_streak
        self.visual_transport = visual_transport
        self.source_preparation = source_preparation
        self.playback_session = playback_session
        self.guided_session = guided_session
        self.score_artifact_registry = score_artifact_registry
        self.attempt = attempt
        self.listen = listen
        self.preprocessing = preprocessing
        self.fingering = fingering
        self.progress = progress
        self.fukuda_mistakes = fukuda_mistakes
        self.library = library
        self.library_health = library_health
        self.flow_session = flow_session
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
        self.visual_transport.clear_take_end()
        self.lifecycle.stop(reason="source_changed")
        self.recovery_streak.clear()
        self.lesson_cursor.set_course_guided(False)
        self.source_identity.install(
            plan=prepared.plan, source=str(prepared.path),
            fingerprint=prepared.fingerprint, warmup=warmup)
        self.lesson_cursor.select_opening(0.0)
        self.score_artifact_registry.invalidate()
        self.source_preparation.source_installed()
        self.playback_session.select_source()
        self.guided_session.clear_selection()
        self.notices.publish("Press Start to practice", "Press Start to practice.")
        self.source_identity.advance_revision()
        self.attempt.reset_source_presentation()
        if self.flow_session.active(self.source_identity.plan, warmup=warmup):
            return prepared.resumed
        return None

    def fingering_status(self) -> dict:
        selected = self.source_identity.plan
        return self.source_preparation.fingering_status(
            selected.piece if selected is not None else None)

    def _apply_listen_failure(self) -> None:
        failure = self.listen.take_failure()
        if failure is not None:
            self.playback_session.wait_for_player()
            self.notices.publish(failure, failure)

    def correct_fingering(self, source_id: str, finger: int | None,
                          *, fingerprint: str | None = None) -> None:
        with self.lock:
            self._apply_listen_failure()
            selected = self.source_identity.plan
            identity = self.source_preparation.capture_correction(
                piece=selected.piece if selected is not None else None,
                fingerprint=self.source_identity.fingerprint,
                requested_fingerprint=fingerprint)
        with self.source_preparation.source_mutation():
            with self.lock:
                selected = self.source_identity.plan
                piece = selected.piece if selected is not None else None
                source_fingerprint = self.source_identity.fingerprint
            corrected = self.source_preparation.correct_fingering(
                identity, piece=piece, fingerprint=source_fingerprint,
                source_id=source_id, finger=finger, fingering=self.fingering)
            with self.lock:
                selected = self.source_identity.plan
                installed = self.source_preparation.correction_install(
                    corrected, piece=selected.piece if selected is not None else None,
                    fingerprint=self.source_identity.fingerprint,
                    score_revision=self.source_identity.revision)
                self._apply_listen_failure()
                selected.piece = installed.piece
                self.score_artifact_registry.invalidate()
                self.source_identity.publish_revision(installed.score_revision)
                if self.playback_session.source_revised(self.source_identity.revision):
                    self.listen.retarget_score(self.source_identity.revision)

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
            self.playback_session.select_source()
            self.lesson_cursor.set_course_guided(False)
            self.notices.publish(
                "Warm-up ready - left, right, then both hands",
                "Three clean passes unlock the next hand.")
            self.progress.save(self.source_identity.plan, self.source_identity.fingerprint)
        self.library.mark_opened(identifier)
