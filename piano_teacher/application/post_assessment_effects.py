"""Apply accepted post-assessment effects and exact saved teaching decisions.

AttemptSettlement retains the only durable write and grading receipt.
This application workflow applies its accepted stage and presentation
effects atomically without choosing another stage, grade or recovery policy.
"""
from __future__ import annotations
from ..application.mistake_responses import resolve_mistake_policy
from ..application.passage_outcome_presenter import performance_next_action


class PostAssessmentEffects:
    def __init__(self, *, source_identity, lesson_cursor, notices,
                 attempt_settlement, teaching_decisions, clock,
                 teaching_continuation, library, visual_transport,
                 attempt, lesson_execution, playback_session,
                 score_artifact_registry, transport_timing,
                 assessment, feedback_seconds):
        self.source_identity, self.lesson_cursor, self.notices = source_identity, lesson_cursor, notices
        self.attempt_settlement, self.teaching_decisions = attempt_settlement, teaching_decisions
        self.clock, self.teaching_continuation = clock, teaching_continuation
        self.library, self.visual_transport, self.attempt = library, visual_transport, attempt
        self.lesson_execution, self.playback_session = lesson_execution, playback_session
        self.score_artifact_registry, self.transport_timing = score_artifact_registry, transport_timing
        self.assessment, self.feedback_seconds = assessment, feedback_seconds

    def commit_pending(self, *, finish_publication: bool = True) -> str:
        if self.attempt_settlement.pending_result is None or self.source_identity.plan is None:
            return ""
        pending = self.attempt_settlement.pending
        decision = pending.decision
        try:
            committed = self.attempt_settlement.commit_full_passage(
                plan=self.source_identity.plan,binding=self.teaching_decisions.binding(),now=self.clock(),
                continuation=self.teaching_continuation,
                policy=resolve_mistake_policy(self.library.settings["mistake_response_strategy"]),
                score_revision=self.source_identity.revision,
                visual_offset=self.visual_transport.visual_offset_beats)
            outcome = committed.receipt
            self.attempt.apply_settlement(committed,plan=self.source_identity.plan)
            if decision.verdict is not None and decision.verdict.clears_trouble:
                self.lesson_execution.reset_trouble()
            if outcome.stage_changed:
                self.lesson_cursor.select_opening(0.0)
                self.source_identity.publish_revision(committed.selection.revision)
                self.playback_session.wait_for_player()
                prebuilt = self.teaching_continuation.consume_committed_asset(
                    committed.prepared,changed=True,auto=self.playback_session.auto,
                    selection=committed.selection)
                if prebuilt is not None:
                    self.score_artifact_registry.adopt(prebuilt)
                else:
                    self.score_artifact_registry.current.invalidate()
                self.visual_transport.adopt_committed_stage(
                    committed,preserved=prebuilt is not None)
            else:
                self.teaching_continuation.consume_committed_asset(
                    None,changed=False,auto=self.playback_session.auto,selection=None)
        except BaseException:
            self.attempt.publication_failed()
            raise
        if finish_publication:
            self.attempt_settlement.finish_publication()
        self.attempt.publication_finished()
        return outcome.message

    def performance_review(self, phrase: Phrase, result) -> dict:
        """Retained engine API; assessment service owns report construction."""
        tempo = self.transport_timing.active_tempo_map()
        elapsed_to_beat = (None if tempo is None else
            lambda seconds: tempo.beat_at(tempo.seconds_at(self.visual_transport.play_from_beat)+seconds))
        return self.assessment.review(
            phrase, result, bar_boundaries=self.source_identity.plan.piece.bar_boundaries,
            played_from_beat=self.visual_transport.play_from_beat, bpm=self.source_identity.plan.bpm,
            elapsed_to_beat=elapsed_to_beat)

    def finish_performance_review(self, phrase: Phrase, result):
        """Publish review only after its evidence and source feedback commit."""
        self.notices.next_action = performance_next_action(
            warmup=self.source_identity.warmup,summary=self.attempt.performance_summary)
        self.playback_session.stop_automatic()

    def finish_section_review(self, result):
        """Complete finish section review after a scored take."""
        # Section reviews are deliberate, bounded practice. Stop at the
        # selected boundary, preserve detailed feedback, and never
        # auto-advance to a different passage.
        self.playback_session.stop_automatic()
        self.attempt.finish_section_review()
        self.visual_transport.finish_rewind()
        self.lesson_cursor.select_opening(0.0)
        self.notices.feedback = "Section review finished · " + result.summary
        self.notices.next_action = "Review the notes or press Start for the whole passage."

    def finish_partial_recovery(self, result, now: float, *, exposure=None):
        """Complete finish partial recovery after a scored take."""
        # A clean *partial* recovery cannot confer full passage mastery.
        # Clear the bounded review before the scheduled full-pass retry.
        self.attempt.prepare_full_retry()
        self.lesson_cursor.select_opening(exposure.from_beat if exposure is not None else 0.0)
        self.transport_timing.schedule_preparation(self.lesson_cursor.opening_beat, now=now,
            from_visual=self.visual_transport.visual_offset_beats + self.visual_transport.play_from_beat
                + self.transport_timing.elapsed_beat(now-self.visual_transport.run_at),
            reverse_seconds=self.feedback_seconds)
        self.notices.feedback = "Selected section finished · " + result.summary
        self.notices.next_action = "Next: play the whole passage from its beginning to earn mastery."

