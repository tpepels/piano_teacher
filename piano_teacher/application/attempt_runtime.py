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
    pending_result: object | None = None
    pending_assessed_bpm: float | None = None
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
        self.pending_result = None
        self.pending_assessed_bpm = None
        self.feedback_marks = []
        self.feedback_unmapped = 0

    def hold_full_result(self, result, bpm: float) -> None:
        """One pending result and source tempo until its durable settlement."""
        self.pending_result = result
        self.pending_assessed_bpm = bpm

    def publish_completion(self, *, marks: list[dict], unmapped: int) -> None:
        self.feedback_marks = marks
        self.feedback_unmapped = unmapped

    def finish_review(self, summary: dict | None, stage_key: str) -> None:
        self.recorder = None
        self.performance_summary = summary
        self.review_stage_identity = stage_key

    def reset_for_stop(self) -> None:
        """Reset every attempt/review/recovery field in one stable owner."""
        self.recorder = None
        self.pending_result = None
        self.pending_assessed_bpm = None
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
