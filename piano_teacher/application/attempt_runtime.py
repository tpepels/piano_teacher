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
    pending_rolling: tuple | None = None
    settlement_failed: bool = False
    performance_summary: dict | None = None
    review_stage_identity: str | None = None
    review_end_beat: float | None = None
    review_session_complete: bool = False
    automatic_remedial_review: bool = False
    retry_range: dict | None = None
    recovery_notice: dict | None = None
    guided_recovery_pending: bool = False

    def begin_take(self, *, recording: bool) -> None:
        """Open one recorder and discard only per-take grading output."""
        self.recorder = Recorder() if recording else None
        self.feedback_marks = []
        self.feedback_unmapped = 0

    def clear_feedback(self) -> None:
        self.feedback_marks = []
        self.feedback_unmapped = 0

    def reset_source_presentation(self) -> None:
        self.clear_feedback()

    def publish_live_marks(self, marks: list[dict]) -> None:
        self.feedback_marks = marks

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

    def reset_for_stop(self) -> None:
        """Reset every attempt/review/recovery field in one stable owner."""
        self.recorder = None
        self.feedback_marks = []
        self.feedback_unmapped = 0
        self.pending_rolling = None
        self.settlement_failed = False
        self.performance_summary = None
        self.review_stage_identity = None
        self.review_end_beat = None
        self.review_session_complete = False
        self.automatic_remedial_review = False
        self.retry_range = None
        self.recovery_notice = None
        self.guided_recovery_pending = False
