"""One stable owner for the mutable lifetime of a graded/practice take.

A piece and its saved progress outlive a take; the captured notes, pending
assessment, feedback marks, rolling checkpoint and review/retry metadata do
not. This object is never replaced while MIDI ingress or the evidence ledger
can still hold references to the active learner.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from ..practice import Recorder


@dataclass(slots=True)
class AttemptRuntime:
    recorder: Recorder | None = None
    feedback_marks: list[dict] = field(default_factory=list)
    feedback_unmapped: int = 0
    performance_summary: dict | None = None
    review_stage_identity: str | None = None
    review_session_complete: bool = False
    retry_range: dict | None = None
    recovery_notice: dict | None = None
    guided_recovery_pending: bool = False
    latest_timing_accuracy: float | None = None

    def begin_timed_review(self) -> None:
        """Clear the previous review when a new graded take begins."""
        self.performance_summary = None
        self.review_stage_identity = None
        self.review_session_complete = False

    def begin_take(self, *, recording: bool) -> None:
        """Open one recorder and discard only per-take grading output."""
        self.recorder = Recorder() if recording else None
        self.feedback_marks = []
        self.feedback_unmapped = 0

    def clear_feedback(self) -> None:
        self.feedback_marks = []
        self.feedback_unmapped = 0

    def suspend_recording(self) -> None:
        self.recorder = None

    def restore_retry(self, selected) -> None:
        self.retry_range = dict(selected) if selected is not None else None

    def prepare_timed_exposure(self, prepared) -> None:
        if prepared.return_context is not None:
            self.restore_retry(prepared.retry_range)

    def reset_source_presentation(self) -> None:
        self.clear_feedback()


    def publish_completion(self, *, marks: list[dict], unmapped: int) -> None:
        self.feedback_marks = marks
        self.feedback_unmapped = unmapped

    def apply_settlement(self, committed, *, plan) -> None:
        """Apply attempt presentation from the exact durable receipt."""
        outcome = committed.receipt
        self.retry_range = None
        if outcome.accelerated:
            self.recovery_notice = {"kind":"speedup", "errors":0,
                "from_bpm":outcome.previous_bpm,"to_bpm":plan.bpm,
                "first_bar":plan.active_phrase.first_bar,
                "last_bar":plan.active_phrase.last_bar,
                "expires_at":committed.committed_at+7.0}
        if outcome.stage_changed:
            self.performance_summary = self.review_stage_identity = None

    def finish_review(self, summary: dict | None, stage_key: str) -> None:
        self.recorder = None
        self.performance_summary = summary
        self.review_stage_identity = stage_key
        if summary is not None and "timing_accuracy_percent" in summary:
            self.latest_timing_accuracy = summary["timing_accuracy_percent"]

    def reset_for_stop(self) -> None:
        """Reset every attempt/review/recovery field in one stable owner."""
        self.recorder = None
        self.feedback_marks = []
        self.feedback_unmapped = 0
        self.performance_summary = None
        self.review_stage_identity = None
        self.review_session_complete = False
        self.retry_range = None
        self.recovery_notice = None
        self.guided_recovery_pending = False
        self.latest_timing_accuracy = None
