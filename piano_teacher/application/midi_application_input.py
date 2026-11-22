"""Single source-bound native MIDI callback, device hot-plug and shortcut route.

MidiIngress remains the sole calibrated timing/grading input boundary;
all events enter PracticeSession under the single application lock.
"""
from __future__ import annotations
import time
from .midi_ingress import MidiInputFacts, InputTransportFacts


class MidiApplicationInput:
    def __init__(self, *, source_identity, visual_transport, playback_session,
                 attempt_settlement, attempt, playback, midi, lock,
                 runtime_timings, device_workflows, teaching_decisions,
                 settings_workflows, library, midi_ingress, transport_timing,
                 live_feedback_workflows, guided_session,
                 timed_playback, clock):
        self.source_identity, self.visual_transport = source_identity, visual_transport
        self.playback_session, self.attempt_settlement, self.attempt = playback_session, attempt_settlement, attempt
        self.playback, self.midi, self.lock = playback, midi, lock
        self.runtime_timings, self.device_workflows = runtime_timings, device_workflows
        self.teaching_decisions, self.settings_workflows = teaching_decisions, settings_workflows
        self.library, self.midi_ingress = library, midi_ingress
        self.transport_timing, self.live_feedback_workflows = transport_timing, live_feedback_workflows
        self.guided_session = guided_session
        self.timed_playback, self.clock = timed_playback, clock
        self._session = None

    def bind_session(self, session) -> None:
        if self._session is not None:
            raise RuntimeError("MIDI adapter already bound")
        self._session = session

    def midi_lost(self, reason: str = "device_disconnected") -> None:
        if self.source_identity.plan is not None:
            self.teaching_decisions.prepare("interrupted", action=reason, store=False)
        self.device_workflows.disconnect(reason)

    def ports(self) -> list[str]:
        if not self.midi.enabled:
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
            received_at = self.clock()
            self._session.on_midi(message, received_at=received_at)
        finally:
            self.runtime_timings.midi_ms.append(
                (time.perf_counter()-began)*1000.0)

    def midi_transport_facts(self) -> InputTransportFacts:
        """Snapshot only the transport gates needed by the one MIDI router."""
        return InputTransportFacts(
            next_at=self.visual_transport.next_at,
            preview_loop_pending=self.visual_transport.preview_loop_pending,
            pending_teaching_result=self.attempt_settlement.pending_result is not None,
            pending_rewind=self.visual_transport.pending_rewind is not None,
            automatic=self.playback_session.auto,preview_only=self.playback_session.preview_only,
            visual_gap_beats=self.visual_transport.visual_gap_beats,
            awaiting_score=self.playback_session.awaiting_score_revision is not None,
            exercise_kind=(self.source_identity.plan.exercise.kind if self.source_identity.plan else ""),
            review_end_beat=self.attempt.review_end_beat,
            presentation_required=self.playback.presentation_required,
            successor_action=(self.playback.intent.action
                if self.playback.intent is not None else None))

    def apply_midi_shortcut(self, effect) -> None:
        # The input adapter cannot change settings or select a lesson action.
        # Route accepted shortcuts through the same serialized session event.
        if self._session is None:
            raise RuntimeError("MIDI shortcut before session binding")
        self._session.on_shortcut(effect)

    def _deliver_message(self, message, *, received_at=None, corrected_at=None, deferred=False):
        now = self.clock() if received_at is None else received_at
        facts = MidiInputFacts(self.source_identity.fingerprint,self.source_identity.revision,
            self.source_identity.plan.identity if self.source_identity.plan else "",self.source_identity.plan.active_phrase if self.source_identity.plan else None,
            self.source_identity.plan.hand if self.source_identity.plan else "both",self.source_identity.plan.bpm if self.source_identity.plan else 60.,
            self.playback_session.mode,self.playback_session.running,self.visual_transport.paused,self.playback_session.preview_only,
            self.visual_transport.play_from_beat,self.visual_transport.run_at,self.playback_session.transport_id,
            self.transport_timing.active_tempo_map(),self.playback_session.running or (self.playback_session.mode == "learn" and self.guided_session.controller is not None))
        self.midi_ingress.dispatch(
            message,facts=facts,received_at=now,
            corrected_at=corrected_at,deferred=deferred,
            midi_offset_seconds=self.library.settings["midi_offset_ms"]/1000.0,
            apply_shortcut=self.apply_midi_shortcut,
            transport_facts=self.midi_transport_facts,
            musical_seconds=self.transport_timing.musical_seconds,
            recorder=lambda: self.attempt.recorder,
            teaching=lambda: self.guided_session.controller,
            feedback_take=self.live_feedback_workflows.feedback_take)

    def poll_midi_connection(self):
        if self.midi.closed:
            self.midi_lost()
        if self.device_workflows.connection_due():
            try:
                self.ports()
            except RuntimeError:
                # Keep actionable device feedback without failing /state.
                pass

