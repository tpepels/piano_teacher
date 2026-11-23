"""Apply source-bound recovery and bounded retry decisions.

The configured AssessmentService policy decides recovery and graded boundaries;
this workflow applies its existing decision to the selected source and
canonical PlaybackSession/VisualTransport without an alternative clock.
"""
from __future__ import annotations
from ..music import Phrase
from ..remediation import RemedialAssignment
from ..lesson_settings import course_rules
from .exposure_preparation import prepare_remedial, prepare_response
from .mistake_responses import resolve_mistake_policy
from .musical_scheduler import SCHEDULER


class RecoveryWorkflows:
    def __init__(self, *, source_identity, lesson_cursor, notices, attempt,
                 playback_session, visual_transport, transport_timing,
                 timed_playback, lesson_execution, exposure_workflows,
                 attempt_settlement, policy_registry, library, recovery_streak,
                 live_feedback_workflows, live_assessment, teaching_decisions,
                 clock, feedback_seconds):
        self.source_identity, self.lesson_cursor = source_identity, lesson_cursor
        self.notices, self.attempt = notices, attempt
        self.playback_session, self.visual_transport = playback_session, visual_transport
        self.transport_timing, self.timed_playback = transport_timing, timed_playback
        self.lesson_execution, self.exposure_workflows = lesson_execution, exposure_workflows
        self.attempt_settlement, self.policy_registry = attempt_settlement, policy_registry
        self.library, self.recovery_streak = library, recovery_streak
        self.live_feedback_workflows, self.live_assessment = live_feedback_workflows, live_assessment
        self.teaching_decisions, self.clock = teaching_decisions, clock
        self.feedback_seconds = feedback_seconds

    def _apply_prepared_recovery(self, prepared, *, now: float,
                                 deadline: float | None = None,
                                 visual_from: float | None = None,
                                 exposure=None) -> None:
        """Execute one source-bound recovery effect, without choosing a policy.

        Both selected whole-response and remedial effects share the same
        cursor, attempt, transport and notice writer. An untimed remedial
        selection prepares a new bounded take; an untimed whole-response
        schedules the original source's normal retry. Guided remediation
        keeps its note-isolation controller without overwriting the active
        timed-retry context.
        """
        if prepared.action not in ("pause", "guided", "continue", "prepare"):
            raise ValueError("Unknown selected recovery action")
        if prepared.action == "continue" and deadline is None:
            raise ValueError("Timed recovery requires a selected deadline")
        if prepared.action == "guided" and prepared.assignment is not None:
            self.lesson_execution.begin_learn(
                from_beat=prepared.start, recovery=True,
                remediation=prepared.assignment, exposure=exposure)
        else:
            if prepared.action == "prepare" and prepared.assignment is not None:
                self.exposure_workflows.prepare_practice(exposure=exposure)
                self.playback_session.wait_for_player()
            self.lesson_cursor.select_opening(prepared.start)
            self.attempt.prepare_recovery(prepared)
            if prepared.action == "pause":
                self.playback_session.stop_automatic()
                self.visual_transport.cancel_preparation()
                self.visual_transport.cancel_continuation()
            elif prepared.action == "guided":
                self.lesson_execution.begin_learn(
                    from_beat=prepared.start, recovery=True,
                    exposure=self.attempt_settlement.pending.decision.next_exposure)
            elif prepared.action == "continue":
                self.timed_playback.continue_at(SCHEDULER.continuation(
                    self.transport_timing.collect_continuation_measurement(
                        deadline, prepared.start),
                    now=self.clock(), bpm=self.transport_timing.presentation_bpm()),
                    from_beat=prepared.start)
            elif prepared.action == "prepare":
                if prepared.assignment is None:
                    self.transport_timing.schedule_preparation(
                        prepared.start, now=now,
                        from_visual=(self.transport_timing.visual_motion(now)[0]
                                     if visual_from is None else visual_from),
                        reverse_seconds=self.feedback_seconds)
            else:
                raise ValueError("Unknown selected recovery action")
        if prepared.feedback:
            self.notices.feedback = prepared.feedback
        if prepared.next_action:
            self.notices.next_action = prepared.next_action

    def apply_policy_response(self, response, *, now: float,
                              deadline: float | None = None,
                              visual_from: float | None = None):
        prepared = prepare_response(
            response,
            source_duration=(self.source_identity.plan.active_phrase.end
                             - self.source_identity.plan.active_phrase.start),
            has_deadline=deadline is not None)
        self._apply_prepared_recovery(
            prepared, now=now, deadline=deadline, visual_from=visual_from)

    def start_remedial_assignment(self, assignment: RemedialAssignment,
                                  *, deadline: float | None = None,
                                  exposure=None) -> None:
        if self.source_identity.plan is None:
            raise ValueError("Remediation requires an installed lesson source")
        prepared = prepare_remedial(
            self.exposure_workflows.source(), assignment, exposure,
            has_deadline=deadline is not None,
            automatic=self.playback_session.auto)
        if prepared is None:
            raise ValueError("Remediation belongs to a superseded source stage")
        self._apply_prepared_recovery(
            prepared, now=self.clock(), deadline=deadline, exposure=exposure)

    def apply_rolling_recovery(self, decision, phrase: Phrase, grid, score_beat: float, now: float):
        """Apply an accepted source-grid recovery decision atomically."""
        # Capture marks at the performance tempo, not at the slower
        # BPM selected for the next retry. Re-scaling the recorded
        # timestamps early would move mistakes to incorrect notes.
        saved = self.attempt_settlement.rolling_record
        if saved is None:
            # The first assessment publishes frozen source-tempo feedback.
            # A persistence/presentation retry must retain those old marks,
            # not recompute them from a new BPM or paused source clock.
            self.attempt.publish_live_marks(
                self.live_feedback_workflows.live_feedback(
                    now-self.visual_transport.run_at))
            self.live_assessment.publish(
                self.attempt.feedback_marks,
                self.live_feedback_workflows.feedback_take())
        outgoing_bpm = self.source_identity.plan.bpm
        scored_end = self.visual_transport.run_at + (
            self.transport_timing.elapsed_seconds(decision.end_beat) -
            self.transport_timing.elapsed_seconds(self.visual_transport.play_from_beat))
        hand = self.source_identity.plan.hand
        notes = self.attempt.recorder.presses if self.attempt.recorder else ()
        from_beat = self.visual_transport.play_from_beat
        score_revision = self.source_identity.revision
        if saved is not None:
            if self.source_identity.revision != saved.take.score_revision:
                raise ValueError(
                    "Rolling take score revision changed before publication retry")
            # A durable decision may already have lowered BPM or changed
            # the stage before visual continuation failed. Resume exactly
            # its original graded take, never reassess a new source/cursor.
            decision, phrase, grid = saved.decision, saved.phrase, saved.grid
            score_beat = saved.score_beat
            outgoing_bpm, scored_end = saved.outgoing_bpm, saved.scored_end
            hand, notes = saved.take.hand, saved.take.played
            from_beat, score_revision = saved.take.from_beat, saved.take.score_revision
        try:
            completed = self.attempt_settlement.complete_rolling(
                decision=decision,phrase=phrase,grid=grid,score_beat=score_beat,
                now=now,bpm=outgoing_bpm,scored_end=scored_end,hand=hand,
                played=notes,from_beat=from_beat,
                tempo=self.transport_timing.active_tempo_map(),policies=self.policy_registry.grading,
                prepare_decision=self.teaching_decisions.prepare,plan=self.source_identity.plan,
                binding=self.teaching_decisions.binding(),
                score_revision=score_revision,
                policy=resolve_mistake_policy(self.library.settings["mistake_response_strategy"]))
        except Exception:
            self.playback_session.finish_take()
            self.playback_session.stop_automatic()
            self.playback_session.freeze_after_fault(now)
            self.notices.fault("Could not save the retry evidence",
                "Check storage, then Resume to save this same attempt.")
            raise
        if completed.transition is None:
            from ..measure_grid import next_chunk_end
            following = next_chunk_end(grid, decision.end_beat)
            self.visual_transport.advance_boundary(following if following > decision.end_beat+1e-7 else 0.)
            return
        try:
            self._install_rolling_recovery(completed, score_beat=score_beat, now=now)
        except Exception:
            # A durable receipt may already have installed some source
            # effects. Stop the old graded clock and keep its pending receipt.
            # Explicit Retry replays only unacknowledged effect names.
            self.playback_session.finish_take()
            self.playback_session.stop_automatic()
            self.playback_session.freeze_after_fault(now)
            self.notices.fault("Could not apply the saved recovery",
                "Press Resume to finish this same saved recovery.")
            raise
        return

    def _install_rolling_recovery(self, completed, *, score_beat: float,
                                  now: float) -> None:
        transition = completed.transition
        outgoing_bpm,scored_end = completed.outgoing_bpm,completed.scored_end
        apply = self.attempt_settlement.rolling_effect
        apply(completed, "tempo", lambda: self.visual_transport.note_tempo(
            stage=self.source_identity.plan.identity,
            bpm=self.transport_timing.presentation_bpm(), now=now))
        short_deadline = None
        if transition.uses_completed_rest:
            apply(completed, "take_end", lambda: self.visual_transport.record_take_end(
                at=scored_end, bpm=outgoing_bpm))
            short_deadline = SCHEDULER.measured_rest(
                self.transport_timing.collect_rest_measurement(
                    from_beat=transition.restart_beat),
                now=now, bpm=self.transport_timing.presentation_bpm())
        apply(completed, "prepare", lambda: self.transport_timing.schedule_preparation(
            transition.restart_beat, now=now,
            from_visual=self.visual_transport.visual_offset_beats + score_beat,
            reverse_seconds=self.feedback_seconds, short_deadline=short_deadline))
        apply(completed, "streak", lambda: self.recovery_streak.record(
            transition.trouble_key, transition.trouble_count))
        apply(completed, "attempt", lambda: self.attempt.apply_recovery(transition))
        if transition.guided:
            # Guided recovery must never re-withdraw an already processed
            # immutable future announcement during a publication retry.
            apply(completed, "withdraw", self.visual_transport.withdraw_announcement)
        def publish_notices():
            self.notices.feedback = transition.feedback
            self.notices.next_action = transition.next_action
        apply(completed, "notices", publish_notices)
        if transition.action == "pause":
            apply(completed, "stop_auto", self.playback_session.stop_automatic)
            apply(completed, "cancel_preparation",
                  self.visual_transport.cancel_preparation)
            apply(completed, "cancel_continuation",
                  self.visual_transport.cancel_continuation)
        self.attempt_settlement.finish_rolling_publication(completed)

    def assess_rolling_boundary(self, boundary: float,
                                 grid: tuple[float, ...]):
        """Grade one authored boundary under the existing session lock."""
        try:
            self.attempt_settlement.checkpoint(
                self.attempt.recorder.presses if self.attempt.recorder else (),
                boundary=boundary)
        except Exception:
            self.playback_session.freeze_after_fault(self.clock())
            self.notices.fault("Could not save the recording checkpoint",
                "Check storage, then Resume to retry this boundary.")
            raise
        if self.lesson_execution.flow_active() or not resolve_mistake_policy(
                self.library.settings["mistake_response_strategy"]).interrupt_rolling:
            # Practice flow: a take always plays to its end (no mid-take rewind).
            return None
        tempo_map = self.transport_timing.active_tempo_map()
        return self.policy_registry.grading.select(tempo_map).recover(
            self.source_identity.plan.active_phrase, hand=self.source_identity.plan.hand, bpm=self.source_identity.plan.bpm,
            played=self.attempt.recorder.presses if self.attempt.recorder else [],
            from_beat=self.visual_transport.play_from_beat, end_beat=boundary, grid=grid,
            threshold=course_rules(
                self.source_identity.plan.lesson_definition.generator_name,
                warmup=self.source_identity.warmup).recovery_errors_in_window,
            warmup=self.source_identity.warmup, tempo=tempo_map)

