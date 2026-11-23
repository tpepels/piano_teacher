"""Read-side projection of current source, transport, score and feedback facts.

Snapshots sample under the application lock; they never start or settle
takes. SessionCapture samples values; ScorePresentation derives score
facts and prepares the Free target; SnapshotExtras adds clock, key and
calibration facts; SessionReadModels composes the published snapshot.
"""
from __future__ import annotations
from dataclasses import replace
from .musical_scheduler import SCHEDULER, SNAPSHOT_LATENCY_SECONDS
from .score_state_publisher import ScoreProjectionFacts
from .control_projection import project_controls
from .session_snapshot_builder import SnapshotValues, capture as capture_session_snapshot
from ..state_projection import SessionSnapshot, project_session_state


class SessionCapture:
    """Sample named values and read ports under the application lock."""

    def __init__(self, *, lesson, notices, take, transport, library,
                 midi_input, score, ports, clock):
        self.lesson = lesson
        self.notices = notices
        self.take = take
        self.transport = transport
        self.library = library
        self.midi_input = midi_input
        self.score = score
        self.ports = ports
        self.clock = clock

    def capture_snapshot(self, *, sampled_at=None) -> SessionSnapshot:
        values = SnapshotValues(
            _guided_recovery_pending=self.take.guided_recovery_pending,
            _guided_return=self.lesson.guided_return_context,
            _remediation_active=self.take.remediation_active,
            auto=self.transport.auto,
            awaiting_score_revision=self.transport.awaiting_score_revision,
            count_in_bar_beats=self.transport.count_in_bar_beats,
            count_in_beats=self.transport.count_in_beats,
            count_in_meter=self.transport.count_in_meter,
            feedback=self.notices.feedback,
            feedback_marks=self.take.feedback_marks,
            feedback_unmapped=self.take.feedback_unmapped,
            fingerprint=self.lesson.fingerprint,
            guided_range=self.lesson.guided_beat_range,
            guided_open_at=self.score.free_target_arrival(
                self.lesson, self.transport),
            metronome=self.library.settings["metronome"],
            midi_input_count=self.midi_input.input_count,
            midi_input_note=self.midi_input.input_note,
            midi_input_at=self.midi_input.input_at,
            midi_connected=self.midi_input.connected,
            midi_device=self.midi_input.device,
            midi_notes=len(self.take.recorder.presses) if self.take.recorder is not None else 0,
            teaching_active=self.lesson.guided_controller is not None,
            mode=self.transport.mode,
            next_action=self.notices.next_action,
            next_at=self.transport.next_at,
            open_from_beat=self.lesson.opening_beat,
            pause_context=self.transport.pause_context,
            paused=self.transport.paused,
            paused_at=self.transport.paused_at,
            pending_result=self.take.pending_result,
            assessment_verdict=(
                self.take.pending.decision.verdict
                if self.take.pending is not None
                and self.take.pending.assessment is self.take.pending_result
                else None),
            pending_rewind=self.transport.pending_rewind,
            performance_summary=self.take.performance_summary,
            persistent_hints=self.lesson.persistent_hints,
            plan=self.lesson.plan,
            play_from_beat=self.transport.play_from_beat,
            practice_preparation=self.transport.practice_preparation,
            recovery_notice=self.take.recovery_notice,
            retry_range=self.take.retry_range,
            review_end_beat=self.take.review_end_beat,
            run_at=self.transport.run_at,
            running=self.transport.running,
            score_revision=self.lesson.revision,
            transport_id=self.transport.transport_id,
            visual_offset_beats=self.transport.visual_offset_beats,
        )
        guided = self.lesson.guided_controller
        reads = replace(self.ports,
            teaching_snapshot=guided.snapshot if guided is not None else None,
            clock=self.clock if sampled_at is None else lambda: sampled_at)
        return capture_session_snapshot(values, reads)


class ScorePresentation:
    """Score projection facts and the Free target's presentation plan."""

    def __init__(self, *, lesson, transport, timing, score,
                 capture, clock):
        self.lesson = lesson
        self.transport = transport
        self.timing = timing
        self.score = score
        self.capture = capture
        self.clock = clock

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
            presentation_bpm=float(self.timing.presentation_bpm()),
            run_at=self.transport.run_at,
            play_from_beat=self.transport.play_from_beat,
            announced=announced,
            announced_deadline=(self.transport.announced_deadline(
                announced[0]) if announced is not None else None),
            announcement_serial=self.transport.announce_serial,
            scheduled_start=self.transport.scheduled_start,
            timeline={"intent":pending,"current":timeline},
            next_count_in_beats=self.timing.next_count_in_beats(),
            next_count_in_meter=tuple(self.timing.next_count_in_meter()),
            continuous_horizon_beats=self.transport.continuous_horizon_beats,
            duration_beats=(self.lesson.display_phrase(learning=self.transport.mode == "learn").end-self.lesson.display_phrase(learning=self.transport.mode == "learn").start
                            if plan is not None else 0.0),
            has_source=plan is not None,
        )

    def prepare_score_presentation(self) -> None:
        if self.lesson.plan is None or self.transport.mode != "learn":
            return
        now = self.clock()
        state = project_session_state(self.capture.capture_snapshot(sampled_at=now))
        pending, timeline = self.transport.snapshot(self.timing.playback_facts())
        self.score.prepare_guided_score(
            state,self.score_facts(pending,timeline),now=now)


class SnapshotExtras:
    """Clock, key, count-in and calibration facts of the published snapshot."""

    def __init__(self, *, lesson, take, transport, timing, library, midi_input):
        self.lesson = lesson
        self.take = take
        self.transport = transport
        self.timing = timing
        self.library = library
        self.midi_input = midi_input

    def add(self, state: dict, now: float) -> None:
        if self.take.pending_result is not None:
            state["bpm"] = self.timing.presentation_bpm()
        if self.lesson.plan is not None:
            epoch = self.transport.tempo_epoch_for(
                stage=self.lesson.plan.identity,bpm=self.timing.presentation_bpm())
            if epoch is not None:
                state["tempo_epoch_ms"] = epoch*1000.0
        if self.lesson.plan is not None:
            beat = self.lesson.plan.active_phrase.start + self.transport.play_from_beat
            if self.transport.running and now >= self.transport.run_at:
                beat += self.timing.elapsed_beat(now - self.transport.run_at)
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
        state["next_count_in_beats"] = self.timing.next_count_in_beats()
        state["next_count_in_meter"] = self.timing.next_count_in_meter()
        state["short_rest_latency_seconds"] = SNAPSHOT_LATENCY_SECONDS
        state["resume_count_in_beat"] = (
            SCHEDULER.seconds_beats(
                calibration_sample_at-self.midi_input.resume_grading_after,
                self.lesson.plan.bpm)
            if self.transport.running and not self.transport.paused
            and calibration_sample_at < self.midi_input.resume_grading_after
            and self.lesson.plan is not None else None)
        state["midi_key_range"] = self.midi_input.key_range_status(self.midi_input.device)
        state["midi_calibration"] = self.midi_input.calibration_snapshot(
            calibration_sample_at)


class SessionReadModels:
    def __init__(self, *, lesson, transport, timing, score, course,
                 capture, presentation, extras, lock, clock):
        self.lesson = lesson
        self.transport = transport
        self.timing = timing
        self.score = score
        self.course = course
        self.capture = capture
        self.presentation = presentation
        self.extras = extras
        self.lock = lock
        self.clock = clock

    def _committed_base(self, now: float) -> tuple[dict, dict | None, dict]:
        """Project the same locked transport/lesson state for all consumers.

        The native button resolver and the frame presenter must not disagree
        about admission, failure or the currently authorized segment.
        """
        state = project_session_state(self.capture.capture_snapshot(sampled_at=now))
        pending, timeline = self.transport.snapshot(self.timing.playback_facts())
        self.score.project_transport_state(
            state, pending, timeline,
            running=self.transport.running,
            paused=self.transport.paused)
        # Physical score admission must authenticate the selected course stage,
        # not infer it from a revision or from a mutable frontend hand label.
        plan = self.lesson.plan
        state["stage_key"] = plan.identity if plan is not None else ""
        if self.lesson.flow_active:
            state["flow"] = self.lesson.flow_status(self.lesson.plan, self.transport.mode)
        return state, pending, timeline

    def control_snapshot(self) -> dict:
        """Read authoritative command facts without engraving or transitions."""
        state, _, _ = self._committed_base(self.clock())
        return state

    def snapshot(self) -> dict:
        with self.lock:
            now = self.clock()
            state, pending, timeline = self._committed_base(now)
            facts = self.presentation.score_facts(pending,timeline)
            self.score.publish_score_state(state, facts)
            self.extras.add(state, now)
            state["controls"] = project_controls(state)
            return state
