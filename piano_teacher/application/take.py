"""The take domain: one owner for the live take and its settlement.

Internals (never referenced outside the domain's own modules):
- runtime: AttemptRuntime, the recorder, feedback marks, review and retry;
- settlement: AttemptSettlement, the immutable result, decision and receipt.

Other modules read take facts through the read-only properties below and
change take state only through these named operations.
"""
from __future__ import annotations


class Take:
    def __init__(self, *, runtime, settlement):
        self._runtime = runtime
        self._settlement = settlement


    # --- Live take: recorder, feedback marks, review and retry state

    def apply_recovery(self, *args, **kwargs):
        return self._runtime.apply_recovery(*args, **kwargs)

    def apply_settlement(self, *args, **kwargs):
        return self._runtime.apply_settlement(*args, **kwargs)

    def assign_remediation(self, *args, **kwargs):
        return self._runtime.assign_remediation(*args, **kwargs)

    @property
    def automatic_remedial_review(self):
        return self._runtime.automatic_remedial_review

    def clear_feedback(self, *args, **kwargs):
        return self._runtime.clear_feedback(*args, **kwargs)

    @property
    def feedback_marks(self):
        return self._runtime.feedback_marks

    @property
    def feedback_unmapped(self):
        return self._runtime.feedback_unmapped

    def finish_review(self, *args, **kwargs):
        return self._runtime.finish_review(*args, **kwargs)

    def finish_section_review(self, *args, **kwargs):
        return self._runtime.finish_section_review(*args, **kwargs)

    @property
    def guided_recovery_pending(self):
        return self._runtime.guided_recovery_pending

    @property
    def performance_summary(self):
        return self._runtime.performance_summary

    def prepare_full_retry(self, *args, **kwargs):
        return self._runtime.prepare_full_retry(*args, **kwargs)

    def prepare_recovery(self, *args, **kwargs):
        return self._runtime.prepare_recovery(*args, **kwargs)

    def prepare_section(self, *args, **kwargs):
        return self._runtime.prepare_section(*args, **kwargs)

    def prepare_timed_exposure(self, *args, **kwargs):
        return self._runtime.prepare_timed_exposure(*args, **kwargs)

    def publication_failed(self, *args, **kwargs):
        return self._runtime.publication_failed(*args, **kwargs)

    def publication_finished(self, *args, **kwargs):
        return self._runtime.publication_finished(*args, **kwargs)

    def publish_completion(self, *args, **kwargs):
        return self._runtime.publish_completion(*args, **kwargs)

    def publish_live_marks(self, *args, **kwargs):
        return self._runtime.publish_live_marks(*args, **kwargs)

    @property
    def recorder(self):
        return self._runtime.recorder

    @property
    def recovery_notice(self):
        return self._runtime.recovery_notice

    @property
    def remediation_active(self):
        return self._runtime.remediation_active

    def reset_for_stop(self, *args, **kwargs):
        return self._runtime.reset_for_stop(*args, **kwargs)

    def reset_source_presentation(self, *args, **kwargs):
        return self._runtime.reset_source_presentation(*args, **kwargs)

    def restore_retry(self, *args, **kwargs):
        return self._runtime.restore_retry(*args, **kwargs)

    @property
    def retry_range(self):
        return self._runtime.retry_range

    @property
    def review_end_beat(self):
        return self._runtime.review_end_beat

    @property
    def review_session_complete(self):
        return self._runtime.review_session_complete

    @property
    def review_stage_identity(self):
        return self._runtime.review_stage_identity

    @property
    def settlement_failed(self):
        return self._runtime.settlement_failed


    # --- Settlement: one immutable result, one decision, one durable receipt

    @property
    def authority_revision(self):
        return self._settlement.authority_revision

    @property
    def course_revision(self):
        return self._settlement.course_revision

    def begin_full_completion(self, *args, **kwargs):
        return self._settlement.begin_full_completion(*args, **kwargs)

    def cancel_settlement(self, *args, **kwargs):
        return self._settlement.cancel(*args, **kwargs)

    @property
    def cancellation_generation(self):
        return self._settlement.cancellation_generation

    def checkpoint_failed_streak(self, *args, **kwargs):
        return self._settlement.checkpoint_failed_streak(*args, **kwargs)

    def checkpoint_rolling(self, *args, **kwargs):
        return self._settlement.checkpoint(*args, **kwargs)

    def command_applied(self, *args, **kwargs):
        return self._settlement.command_applied(*args, **kwargs)

    def commit_full_passage(self, *args, **kwargs):
        return self._settlement.commit_full_passage(*args, **kwargs)

    def complete_rolling(self, *args, **kwargs):
        return self._settlement.complete_rolling(*args, **kwargs)

    def complete_take(self, *args, **kwargs):
        return self._settlement.complete_take(*args, **kwargs)

    def effects_applied(self, *args, **kwargs):
        return self._settlement.effects_applied(*args, **kwargs)

    @property
    def feedback_pending(self):
        return self._settlement.feedback_pending

    def finish_full_completion(self, *args, **kwargs):
        return self._settlement.finish_full_completion(*args, **kwargs)

    def finish_preview(self, *args, **kwargs):
        return self._settlement.finish_preview(*args, **kwargs)

    def finish_publication(self, *args, **kwargs):
        return self._settlement.finish_publication(*args, **kwargs)

    def finish_rolling_publication(self, *args, **kwargs):
        return self._settlement.finish_rolling_publication(*args, **kwargs)

    def interrupt_current(self, *args, **kwargs):
        return self._settlement.interrupt_current(*args, **kwargs)

    @property
    def pending(self):
        return self._settlement.pending

    @property
    def pending_assessed_bpm(self):
        return self._settlement.pending_assessed_bpm

    @property
    def pending_full_completion(self):
        return self._settlement.pending_full_completion

    @property
    def pending_result(self):
        return self._settlement.pending_result

    @property
    def pending_rolling(self):
        return self._settlement.pending_rolling

    def prepare_settlement(self, *args, **kwargs):
        return self._settlement.prepare(*args, **kwargs)

    def publishing(self, *args, **kwargs):
        return self._settlement.publishing(*args, **kwargs)

    def reset_piece_path(self, *args, **kwargs):
        return self._settlement.reset_piece_path(*args, **kwargs)

    def rolling_effect(self, *args, **kwargs):
        return self._settlement.rolling_effect(*args, **kwargs)

    @property
    def rolling_record(self):
        return self._settlement.rolling_record

    def seal_guided_preparation(self, *args, **kwargs):
        return self._settlement.seal_guided_preparation(*args, **kwargs)
