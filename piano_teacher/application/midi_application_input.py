"""Physical MIDI in three owners: device connection, callback, delivery.

MidiCallback stamps each hardware message on arrival and hands it to the
serialized PracticeSession. MidiDelivery routes an admitted message
through MidiIngress (the sole calibrated timing/grading boundary).
MidiDeviceConnection scans, selects and recovers the device.
"""
from __future__ import annotations
import time
from .midi_ingress import MidiInputFacts, InputTransportFacts


class MidiCallback:
    """The driver callback; never waits for state before stamping time."""

    def __init__(self, *, runtime_timings, clock):
        self.runtime_timings = runtime_timings
        self.clock = clock
        self._session = None

    def bind_session(self, session) -> None:
        if self._session is not None:
            raise RuntimeError("MIDI adapter already bound")
        self._session = session

    def receive(self, message):
        began = time.perf_counter()
        try:
            if self._session is None:
                raise RuntimeError("MIDI event before session binding")
            # Capture the physical callback timestamp before waiting for
            # PracticeSession's lock. Otherwise a source import, settlement
            # or long command could falsely move this attack to a later
            # beat or an adjacent take.
            arrival = self._session.midi_arrival()
            received_at = self.clock()
            # The callback cannot hold onto a mutable driver-owned message
            # while it waits for the session's lock.
            self._session.on_midi(
                message.copy(), received_at=received_at, arrival=arrival)
        finally:
            self.runtime_timings.midi_ms.append(
                (time.perf_counter()-began)*1000.0)

    def apply_shortcut(self, effect) -> None:
        # The input adapter cannot change settings or select a lesson action.
        # Route accepted shortcuts through the same serialized session event.
        if self._session is None:
            raise RuntimeError("MIDI shortcut before session binding")
        self._session.on_shortcut(effect)


class MidiDelivery:
    """Route one admitted, timestamped message to grading/Free/shortcuts."""

    def __init__(self, *, lesson, transport, take, midi_input, score, library,
                 transport_timing, live_feedback_workflows, notices,
                 apply_shortcut):
        self.lesson = lesson
        self.transport = transport
        self.take = take
        self.midi_input = midi_input
        self.score = score
        self.library = library
        self.transport_timing = transport_timing
        self.live_feedback_workflows = live_feedback_workflows
        self.notices = notices
        self.apply_shortcut = apply_shortcut

    def midi_transport_facts(self) -> InputTransportFacts:
        """Snapshot only the transport gates needed by the one MIDI router."""
        return InputTransportFacts(
            continuation_pending=self.transport.continuation_pending,
            pending_teaching_result=self.take.pending_result is not None,
            pending_rewind=self.transport.pending_rewind is not None,
            automatic=self.transport.auto,
            visual_gap_beats=self.transport.visual_gap_beats,
            awaiting_score=self.transport.awaiting_score_revision is not None,
            exercise_kind=(self.lesson.plan.exercise.kind if self.lesson.plan else ""),
            successor_action=(self.transport.intent.action
                if self.transport.intent is not None else None))

    def corrected_time(self, received_at: float,
                       corrected_at: float | None = None) -> float:
        """Apply the selected physical MIDI calibration to its arrival time."""
        return (received_at - self.library.settings["midi_offset_ms"]/1000.0
                if corrected_at is None else corrected_at)

    def deliver(self, message, *, received_at: float, corrected_at=None,
                deferred=False):
        facts = MidiInputFacts(self.lesson.fingerprint,self.lesson.revision,
            self.lesson.plan.identity if self.lesson.plan else "",self.lesson.plan.active_phrase if self.lesson.plan else None,
            self.lesson.plan.hand if self.lesson.plan else "both",self.lesson.plan.bpm if self.lesson.plan else 60.,
            self.transport.mode,self.transport.running,self.transport.paused,
            self.transport.play_from_beat,self.transport.run_at,self.transport.transport_id,
            self.transport_timing.active_tempo_map(),self.transport.running or (self.transport.mode == "learn" and self.lesson.guided_controller is not None),
            self.take.cancellation_generation,
            self.midi_input.device,
            self.score.free_keys_open_at(self.lesson, self.transport))
        early = self.midi_input.dispatch_midi(
            message,facts=facts,received_at=received_at,
            corrected_at=corrected_at,deferred=deferred,
            midi_offset_seconds=self.library.settings["midi_offset_ms"]/1000.0,
            apply_shortcut=self.apply_shortcut,
            transport_facts=self.midi_transport_facts,
            musical_seconds=self.transport_timing.musical_seconds,
            recorder=lambda: self.take.recorder,
            teaching=lambda: self.lesson.guided_controller,
            feedback_take=self.live_feedback_workflows.feedback_take)
        if early:
            # A key during the count-in, or before a Free target reaches the
            # line, earns no credit; say so instead of silently ignoring it.
            self.notices.flash(
                "Wait until the note reaches the line" if self.transport.mode == "learn"
                else "Too early – wait for the count-in, then play")


class MidiDeviceConnection:
    """Scan, select, restore and lose the physical MIDI device."""

    def __init__(self, *, lesson, midi_input, device_workflows,
                 settings_workflows, pause_resume, receive, lock):
        self.lesson = lesson
        self.midi_input = midi_input
        self.device_workflows = device_workflows
        self.settings_workflows = settings_workflows
        self.pause_resume = pause_resume
        self.receive = receive
        self.lock = lock

    def midi_lost(self, reason: str = "device_disconnected") -> None:
        if self.lesson.plan is not None:
            self.lesson.prepare_decision("interrupted", action=reason, store=False)
        self.device_workflows.disconnect(reason)

    def ports(self) -> list[str]:
        if not self.midi_input.enabled:
            return []
        with self.lock:
            scan = self.device_workflows.scan()
            if scan.lost:
                self.midi_lost()
            self.device_workflows.handle_scan_error(scan)
            self.device_workflows.restore_preferred(
                scan.names, callback=self.receive)
            return list(scan.names)

    def connect(self, name: str):
        with self.lock:
            self.device_workflows.select(name, callback=self.receive)
            self.settings_workflows.update(
                {"midi_device": name},pause_current=self.pause_resume.pause)

    def poll_midi_connection(self):
        if self.midi_input.device_closed:
            self.midi_lost()
        if self.device_workflows.connection_due():
            try:
                self.ports()
            except RuntimeError:
                # Keep actionable device feedback without failing /state.
                pass
