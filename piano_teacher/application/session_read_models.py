"""Read-side projection of current source, transport, score and feedback facts.

Snapshots sample under the application lock; they never start or settle takes.
"""
from __future__ import annotations
from .musical_scheduler import SCHEDULER, SNAPSHOT_LATENCY_SECONDS
from .score_state_publisher import ScoreProjectionFacts
from .control_projection import project_controls
from .session_snapshot_builder import SnapshotValues, SnapshotReadPorts, capture as capture_session_snapshot
from ..state_projection import SessionSnapshot, project_session_state


class SessionReadModels:
    def __init__(self, *, lesson, notices, attempt,
                 transport,
                 attempt_settlement, library, midi, midi_ingress,
                 midi_key_shortcuts, midi_calibration, attempt_progression,
                 score_state_publisher, lesson_execution, score_read,
                 listen, live_input, live_assessment, lock, clock,
                 phase, elapsed_beat, visual_motion, tempo_map,
                 next_count_in_beats, next_count_in_meter,
                 start_rate_bpm, presentation_bpm, playback_facts):
        self.lesson = lesson
        self.notices, self.attempt = notices, attempt
        self.transport = transport
        self.attempt_settlement, self.library = attempt_settlement, library
        self.midi, self.midi_ingress = midi, midi_ingress
        self.midi_key_shortcuts, self.midi_calibration = midi_key_shortcuts, midi_calibration
        self.attempt_progression = attempt_progression
        self.score_state_publisher = score_state_publisher
        self.lesson_execution, self.score_read = lesson_execution, score_read
        self.listen, self.live_input, self.live_assessment = listen, live_input, live_assessment
        self.lock, self.clock = lock, clock
        self.phase, self.elapsed_beat = phase, elapsed_beat
        self.visual_motion, self.tempo_map = visual_motion, tempo_map
        self.next_count_in_beats, self.next_count_in_meter = next_count_in_beats, next_count_in_meter
        self.start_rate_bpm, self.presentation_bpm = start_rate_bpm, presentation_bpm
        self.playback_facts = playback_facts

    def live_marks(self, _elapsed_seconds: float) -> list[dict]:
        return (list(self.live_assessment.latest_marks)
                if self.transport.running else [])

    def score_facts(self, pending, timeline) -> ScoreProjectionFacts:
        announced = self.transport.announced_continuation
        plan = self.lesson.plan
        return ScoreProjectionFacts(
            fingerprint=self.lesson.fingerprint,
            stage_key=plan.identity if plan is not None else "",
            revision=self.lesson.revision,
            transport_id=self.transport.transport_id,
            mode=self.transport.mode,
            running=self.transport.running,
            paused=self.transport.paused,
            awaiting_score=self.transport.awaiting_score_revision is not None,
            bpm=float(plan.bpm) if plan is not None else 0.0,
            presentation_bpm=float(self.presentation_bpm()),
            run_at=self.transport.run_at,
            play_from_beat=self.transport.play_from_beat,
            announced=announced,
            announced_deadline=(self.transport.announced_deadline(
                announced[0]) if announced is not None else None),
            announcement_serial=self.transport.announce_serial,
            scheduled_start=self.transport.scheduled_start,
            timeline={"intent":pending,"current":timeline},
            next_count_in_beats=self.next_count_in_beats(),
            next_count_in_meter=tuple(self.next_count_in_meter()),
            continuous_horizon_beats=self.transport.continuous_horizon_beats,
            duration_beats=(self.lesson_execution.display_phrase().end-self.lesson_execution.display_phrase().start
                            if plan is not None else 0.0),
            has_source=plan is not None,
        )

    def prepare_score_presentation(self) -> None:
        if self.lesson.plan is None or self.transport.mode != "learn":
            return
        now = self.clock()
        state = project_session_state(self.capture_snapshot(sampled_at=now))
        pending, timeline = self.transport.snapshot(self.playback_facts())
        self.score_state_publisher.prepare_guided(
            state,self.score_facts(pending,timeline),now=now)

    def _committed_base(self, now: float) -> tuple[dict, dict | None, dict]:
        """Project the same locked transport/lesson state for all consumers.

        The native button resolver and the frame presenter must not disagree
        about admission, failure or the currently authorized segment.
        """
        state = project_session_state(self.capture_snapshot(sampled_at=now))
        pending, timeline = self.transport.snapshot(self.playback_facts())
        self.score_state_publisher.project_transport_state(
            state, pending, timeline,
            running=self.transport.running,
            paused=self.transport.paused)
        # Physical score admission must authenticate the selected course stage,
        # not infer it from a revision or from a mutable frontend hand label.
        plan = self.lesson.plan
        state["stage_key"] = plan.identity if plan is not None else ""
        if self.lesson_execution.flow_active():
            state["flow"] = self.lesson_execution.flow_state()
        return state, pending, timeline

    def control_snapshot(self) -> dict:
        """Read authoritative command facts without engraving or transitions."""
        state, _, _ = self._committed_base(self.clock())
        return state

    def snapshot(self) -> dict:
        with self.lock:
            now = self.clock()
            state, pending, timeline = self._committed_base(now)
            facts = self.score_facts(pending,timeline)
            self.score_state_publisher.publish(state, facts)
            if self.attempt_settlement.pending_result is not None:
                state["bpm"] = self.presentation_bpm()
            state["mistake_response_strategy"] = self.library.settings["mistake_response_strategy"]
            if self.lesson.plan is not None:
                epoch = self.transport.tempo_epoch_for(
                    stage=self.lesson.plan.identity,bpm=self.presentation_bpm())
                if epoch is not None:
                    state["tempo_epoch_ms"] = epoch*1000.0
            if self.lesson.plan is not None:
                beat = self.lesson.plan.active_phrase.start + self.transport.play_from_beat
                if self.transport.running and now >= self.transport.run_at:
                    beat += self.elapsed_beat(now - self.transport.run_at)
                keys = [key for key in self.lesson.plan.piece.key_signatures
                        if key.beat <= beat + 1e-7
                        and key.hand in ("both", self.lesson.plan.hand)]
                state["key_fifths"] = keys[-1].fifths if keys else 0
            # A score-free Settings screen still needs an authoritative
            # backend clock epoch for its MIDI tap calibration. Midpoint-only
            # UI extrapolation drifts when score and device requests queue.
            calibration_sample_at = now
            state.setdefault("clock_sampled_at_ms", calibration_sample_at * 1000.0)
            state["midi_offset_ms"] = self.library.settings["midi_offset_ms"]
            state["next_count_in_beats"] = self.next_count_in_beats()
            state["next_count_in_meter"] = self.next_count_in_meter()
            state["short_rest_latency_seconds"] = SNAPSHOT_LATENCY_SECONDS
            state["resume_count_in_beat"] = (
                SCHEDULER.seconds_beats(
                    calibration_sample_at-self.midi_ingress.resume_grading_after,
                    self.lesson.plan.bpm)
                if self.transport.running and not self.transport.paused
                and calibration_sample_at < self.midi_ingress.resume_grading_after
                and self.lesson.plan is not None else None)
            state["midi_key_range"] = self.midi_key_shortcuts.status(self.midi.device)
            state["midi_calibration"] = self.midi_calibration.snapshot(
                calibration_sample_at)
            state["controls"] = project_controls(state)
            return state

    def capture_snapshot(self, *, sampled_at=None) -> SessionSnapshot:
        """Sample named read ports under the existing application lock."""
        values = SnapshotValues(
            _guided_recovery_pending=self.attempt.guided_recovery_pending,
            _guided_return=self.lesson.guided_return_context,
            _remediation_active=self.attempt.remediation_active,
            auto=self.transport.auto,
            awaiting_score_revision=self.transport.awaiting_score_revision,
            count_in_bar_beats=self.transport.count_in_bar_beats,
            count_in_beats=self.transport.count_in_beats,
            count_in_meter=self.transport.count_in_meter,
            feedback=self.notices.feedback,
            feedback_marks=self.attempt.feedback_marks,
            feedback_unmapped=self.attempt.feedback_unmapped,
            fingerprint=self.lesson.fingerprint,
            guided_range=self.lesson.guided_beat_range,
            is_builtin_warmup=self.lesson.warmup,
            metronome=self.library.settings["metronome"],
            midi_input_count=self.midi.input_count,
            midi_input_note=self.midi.input_note,
            midi_input_at=self.midi.input_at,
            midi_connected=self.midi.connected,
            midi_device=self.midi.device,
            midi_notes=len(self.attempt.recorder.presses) if self.attempt.recorder is not None else 0,
            teaching_active=self.lesson.guided_controller is not None,
            mode=self.transport.mode,
            next_action=self.notices.next_action,
            next_at=self.transport.next_at,
            open_from_beat=self.lesson.opening_beat,
            pause_context=self.transport.pause_context,
            paused=self.transport.paused,
            paused_at=self.transport.paused_at,
            pending_result=self.attempt_settlement.pending_result,
            assessment_verdict=(
                self.attempt_settlement.pending.decision.verdict
                if self.attempt_settlement.pending is not None
                and self.attempt_settlement.pending.assessment is self.attempt_settlement.pending_result
                else None),
            pending_rewind=self.transport.pending_rewind,
            performance_summary=self.attempt.performance_summary,
            persistent_hints=self.lesson.persistent_hints,
            plan=self.lesson.plan,
            play_from_beat=self.transport.play_from_beat,
            practice_preparation=self.transport.practice_preparation,
            preview_only=self.transport.preview_only,
            recovery_notice=self.attempt.recovery_notice,
            retry_range=self.attempt.retry_range,
            review_end_beat=self.attempt.review_end_beat,
            run_at=self.transport.run_at,
            running=self.transport.running,
            score_revision=self.lesson.revision,
            transport_id=self.transport.transport_id,
            visual_offset_beats=self.transport.visual_offset_beats,
        )
        reads = SnapshotReadPorts(
            seek_grid=self.lesson_execution.seek_grid,
            learner_snapshot=self.lesson_execution.learner_snapshot,
            elapsed_beat=self.elapsed_beat,
            phase=self.phase,
            source_model=self.score_read.source_model,
            live_feedback=self.live_marks,
            visual_motion=self.visual_motion,
            active_tempo_map=self.tempo_map,
            display_phrase=self.lesson_execution.display_phrase,
            guided_marks=self.score_read.guided_marks,
            listen_snapshot=self.listen.snapshot,
            live_input_snapshot=self.live_input.snapshot,
            preparation_schedule=self.transport.preparation_schedule,
            teaching_snapshot=self.lesson.guided_controller.snapshot if self.lesson.guided_controller is not None else None,
            clock=self.clock if sampled_at is None else lambda: sampled_at,
        )
        return capture_session_snapshot(values, reads)

