"""Single source-bound native MIDI callback, device hot-plug and shortcut route.

MidiIngress remains the sole calibrated timing/grading input boundary;
all events enter PracticeSession under the single application lock.
"""
from __future__ import annotations
import time
from .midi_ingress import MidiInputFacts, InputTransportFacts


class MidiApplicationInput:
    def __init__(self, *, lesson, transport, take, midi_input, score, lock,
                          runtime_timings, device_workflows,
                          settings_workflows, library, transport_timing,
                          live_feedback_workflows, timed_playback, notices,
                          clock):
        self.lesson = lesson
        self.transport = transport
        self.take = take
        self.score = score
        self.lock = lock
        self.midi_input = midi_input
        self.runtime_timings, self.device_workflows = runtime_timings, device_workflows
        self.settings_workflows = settings_workflows
        self.library = library
        self.transport_timing, self.live_feedback_workflows = transport_timing, live_feedback_workflows
        self.timed_playback, self.clock = timed_playback, clock
        self.notices = notices
        self._session = None

    def bind_session(self, session) -> None:
        if self._session is not None:
            raise RuntimeError("MIDI adapter already bound")
        self._session = session

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
                {"midi_device": name},pause_current=self.timed_playback.pause)

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

    def midi_transport_facts(self) -> InputTransportFacts:
        """Snapshot only the transport gates needed by the one MIDI router."""
        return InputTransportFacts(
            next_at=self.transport.next_at,
            preview_loop_pending=self.transport.preview_loop_pending,
            pending_teaching_result=self.take.pending_result is not None,
            pending_rewind=self.transport.pending_rewind is not None,
            automatic=self.transport.auto,preview_only=self.transport.preview_only,
            visual_gap_beats=self.transport.visual_gap_beats,
            awaiting_score=self.transport.awaiting_score_revision is not None,
            exercise_kind=(self.lesson.plan.exercise.kind if self.lesson.plan else ""),
            review_end_beat=self.take.review_end_beat,
            successor_action=(self.transport.intent.action
                if self.transport.intent is not None else None))

    def apply_midi_shortcut(self, effect) -> None:
        # The input adapter cannot change settings or select a lesson action.
        # Route accepted shortcuts through the same serialized session event.
        if self._session is None:
            raise RuntimeError("MIDI shortcut before session binding")
        self._session.on_shortcut(effect)

    def corrected_time(self, received_at: float,
                       corrected_at: float | None = None) -> float:
        """Apply the selected physical MIDI calibration to its arrival time."""
        return (received_at - self.library.settings["midi_offset_ms"]/1000.0
                if corrected_at is None else corrected_at)

    def deliver(self, message, *, received_at=None, corrected_at=None, deferred=False):
        now = self.clock() if received_at is None else received_at
        facts = MidiInputFacts(self.lesson.fingerprint,self.lesson.revision,
            self.lesson.plan.identity if self.lesson.plan else "",self.lesson.plan.active_phrase if self.lesson.plan else None,
            self.lesson.plan.hand if self.lesson.plan else "both",self.lesson.plan.bpm if self.lesson.plan else 60.,
            self.transport.mode,self.transport.running,self.transport.paused,self.transport.preview_only,
            self.transport.play_from_beat,self.transport.run_at,self.transport.transport_id,
            self.transport_timing.active_tempo_map(),self.transport.running or (self.transport.mode == "learn" and self.lesson.guided_controller is not None),
            self.take.cancellation_generation,
            self.midi_input.device,
            self.score.guided_open_at((
                self.lesson.fingerprint,
                self.lesson.plan.identity if self.lesson.plan else "",
                self.lesson.revision, self.transport.transport_id))
            if self.transport.mode == "learn" else None)
        early = self.midi_input.dispatch_midi(
            message,facts=facts,received_at=now,
            corrected_at=corrected_at,deferred=deferred,
            midi_offset_seconds=self.library.settings["midi_offset_ms"]/1000.0,
            apply_shortcut=self.apply_midi_shortcut,
            transport_facts=self.midi_transport_facts,
            musical_seconds=self.transport_timing.musical_seconds,
            recorder=lambda: self.take.recorder,
            teaching=lambda: self.lesson.guided_controller,
            feedback_take=self.live_feedback_workflows.feedback_take)
        if early:
            # A key before its notes can be played earns no credit; say so
            # instead of silently ignoring it.
            self.notices.feedback = "Too early – wait for the count-in, then play"

    def poll_midi_connection(self):
        if self.midi_input.device_closed:
            self.midi_lost()
        if self.device_workflows.connection_due():
            try:
                self.ports()
            except RuntimeError:
                # Keep actionable device feedback without failing /state.
                pass

