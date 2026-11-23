"""One transactional application boundary for learner history and path reset.

Deleting durable records and replacing the installed plan are one ordered
application operation. The musical transport is stopped by SessionLifecycle;
this service does not own a grading clock, choose lessons or access the engine.
"""
from __future__ import annotations

from pathlib import Path
from ..learning import LearningPlan


class HistoryManagement:
    def __init__(self, *, lesson, notices, progress, measurement,
                          recovery_streak, lifecycle, take, transport, score,
                          learning_evidence, clock, data_dir):
        self.lesson = lesson
        self.notices = notices
        self.progress = progress
        self.measurement = measurement
        self.recovery_streak = recovery_streak
        self.lifecycle = lifecycle
        self.take = take
        self.transport = transport
        self.score = score
        self.learning_evidence = learning_evidence
        self.clock = clock
        self.data_dir = data_dir

    def status(self) -> dict:
        return self.learning_evidence.history_status(
            fingerprint=self.lesson.fingerprint, data_dir=self.data_dir)

    def statistics(self, fingerprint: str | None = None, *, query=None) -> dict:
        # The evidence reader uses its own WAL transaction, outside the tick lock.
        return self.learning_evidence.statistics(fingerprint, query=query)

    def export(self, path: str, *, include_detail: bool = False) -> dict:
        if not isinstance(path, str) or not path.strip() or type(include_detail) is not bool:
            raise ValueError("Choose an export file and detail preference")
        return self.progress.ledger.export(
            Path(path).expanduser(), include_detail=include_detail)

    def _replacement(self) -> LearningPlan | None:
        selected = self.lesson.plan
        if selected is None:
            return None
        return LearningPlan(
            selected.piece,
            warmup=self.lesson.warmup,
            exercise_strategy=selected.exercise_strategy.name,
            fukuda_mistakes=frozenset(), feedback={})

    def _publish_deleted(self, replacement: LearningPlan | None, *,
                         feedback: str) -> dict:
        self.lesson.replace_plan(replacement)
        self.recovery_streak.clear()
        self.lesson.select_opening(0.0)
        self.transport.select_source()
        self.lesson.clear_guided_selection()
        self.score.invalidate_artifacts()
        self.lesson.advance_revision()
        self.notices.feedback = feedback
        self.lesson.set_course_guided(False)
        self.lesson.set_hints(False, now=self.clock())
        return self.status()

    def delete_piece(self, fingerprint: str, *, confirm: bool = False) -> dict:
        if confirm is not True or self.lesson.plan is None or fingerprint != self.lesson.fingerprint:
            raise ValueError("Confirm deletion for the currently loaded piece")
        replacement = self._replacement()
        with self.measurement.atomic():
            self.progress.ledger.delete_piece(fingerprint)
        self.measurement.discard_deleted()
        self.lifecycle.stop(reason="delete_piece_history", persist_evidence=False)
        return self._publish_deleted(
            replacement, feedback="Piece history and learning progress deleted")

    def delete_learner(self, *, confirm: bool = False) -> dict:
        if confirm is not True:
            raise ValueError("Confirm deletion of all learning history and progress")
        replacement = self._replacement()
        with self.measurement.atomic():
            self.progress.ledger.delete_learner()
        self.measurement.discard_deleted()
        self.lifecycle.stop(reason="delete_learner_history", persist_evidence=False)
        # The capture object is still held by MIDI, assessment and evidence.
        self.measurement.begin_fresh_learner_session()
        return self._publish_deleted(
            replacement, feedback="All learning history and progress deleted")

    def reset_current_path(self, *, fingerprint: str, confirm: bool) -> None:
        selected = self.lesson.plan
        if selected is None or not self.lesson.fingerprint:
            raise ValueError("Open a piece before resetting its lesson path")
        if confirm is not True or fingerprint != self.lesson.fingerprint:
            raise ValueError("Confirm the reset for the currently loaded piece")
        replacement = self._replacement()
        self.take.reset_piece_path(
            fingerprint=fingerprint, replacement=replacement,
            played=(self.take.recorder.presses if self.take.recorder
                    else self.measurement.guided.presses),
            now=self.clock())
        self.lifecycle.stop(reason="lesson_reset", persist_evidence=False)
        self.recovery_streak.clear()
        self.lesson.replace_plan(replacement)
        self.lesson.select_opening(0.0)
        self.lesson.set_course_guided(False)
        self.transport.select_source()
        self.lesson.clear_guided_selection()
        self.score.invalidate_artifacts()
        self.lesson.advance_revision()
        self.transport.wait_for_player()
        self.notices.publish(
            "Lesson path reset to its first step",
            "Press Play when you are ready.")
