"""Per-tick observations before any musical transition is decided.

Polls the MIDI device, advances key calibration, surfaces a Listen audio
failure, and records the current evidence phase. Returns the tick's now.
"""
from __future__ import annotations
from .learning_capture import CapturePhaseFacts


class TickObservations:
    def __init__(self, *, lesson, transport, take, midi_input,
                 exposure_workflows, measurement, poll_midi, clock):
        self.lesson = lesson
        self.transport = transport
        self.take = take
        self.midi_input = midi_input
        self.exposure_workflows = exposure_workflows
        self.measurement = measurement
        self.poll_midi = poll_midi
        self.clock = clock

    def observe(self) -> float:
        self.poll_midi()
        self.midi_input.advance_calibration(self.clock())
        self.exposure_workflows.apply_listen_failure()
        now = self.clock()
        learning = self.transport.mode == "learn"
        guided_completed = bool(
            learning and self.lesson.guided_controller is not None
            and self.lesson.guided_controller.snapshot(now=now)["completed"])
        self.measurement.observe_phase(CapturePhaseFacts(
            paused=self.transport.paused,learning=learning,
            awaiting_score=self.transport.awaiting_score_revision is not None,
            guided_completed=guided_completed,running=self.transport.running,
            count_in_activation=max(
                self.transport.run_at,
                self.midi_input.resume_grading_after),
            mode=self.transport.mode,preview=self.transport.preview_only,
            pending_result=self.take.pending_result is not None,
            preparation_pending=self.transport.preparation_pending,
            performance_complete=self.take.performance_summary is not None),now)
        return now
