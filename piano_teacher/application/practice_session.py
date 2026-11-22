"""Single serialized application entrypoint for commands, MIDI and ticks.

The native worker and physical MIDI callback share the existing RLock and
the same active musical source. Lesson/transport/assessment owners retain
their decisions; the session sequences their effects and publications.
"""
from __future__ import annotations
import time
from .control_dispatch import ControlDispatcher
from .control_projection import UI_INTENTS, resolve_ui_intent, project_command_outcome
from .stage_change import prepare_stage_change


from .session_events import (
    TimedStartRequested,
    UserCommand,
    ClockAdvanced,
    MidiShortcut,
    PhysicalMidi,
    PresentationRequired,
    PlaybackReserved,
    PlaybackPresented,
    PlaybackWithdrawn,
    PlaybackFailed,
    SourceCommitted,
    FingeringCorrectionCommitted,
    SettingsChanged,
    DeviceSelected,
    PreloadReady,
    PreloadFailed,
    CalibrationRequested,
    HardwareRequested,
    HistoryExported,
    PieceHistoryDeleted,
    LearnerHistoryDeleted,
    SessionClosed,
    PracticeEvent,
)

class PracticeSession:
    def __init__(self, *,
                 attempt, attempt_settlement, device_workflows, exposure_workflows,
                 history_management, learning_commands, lock, measurement,
                 midi, midi_key_shortcuts, playback_session, read_models,
                 session_commands, settings_workflows, source_identity, teaching_decisions,
                 timed_playback, transport_commands, visual_transport,
                 timeline, midi_ingress, midi_application_input, runtime_timings,
                 source_workflows, lesson_execution, score_preload,
                 lifecycle, progress):
        self.attempt = attempt
        self.attempt_settlement = attempt_settlement
        self.device_workflows = device_workflows
        self.exposure_workflows = exposure_workflows
        self.history_management = history_management
        self.learning_commands = learning_commands
        self.lock = lock
        self.measurement = measurement
        self.midi = midi
        self.midi_key_shortcuts = midi_key_shortcuts
        self.playback_session = playback_session
        self.read_models = read_models
        self.session_commands = session_commands
        self.settings_workflows = settings_workflows
        self.source_identity = source_identity
        self.teaching_decisions = teaching_decisions
        self.timed_playback = timed_playback
        self.transport_commands = transport_commands
        self.visual_transport = visual_transport
        self.timeline = timeline
        self.midi_ingress = midi_ingress
        self.midi_application_input = midi_application_input
        self.runtime_timings = runtime_timings
        self.source_workflows = source_workflows
        self.lesson_execution = lesson_execution
        self.score_preload = score_preload
        self.lifecycle = lifecycle
        self.progress = progress

    def calibration_action(self, action: str) -> None:
        changes = self.device_workflows.calibrate(
            action, stop_reason=self.session_commands.action_reason)
        if changes is not None:
            self.settings_workflows.update(
                changes, pause_current=self.timed_playback.pause)

    def _apply_command(self, action: str, **kwargs) -> dict:
        if action in UI_INTENTS:
            ready = kwargs.pop("score_ready", None)
            error = kwargs.pop("score_error", "")
            score_revision = kwargs.pop("score_revision", None)
            score_fingerprint = kwargs.pop("score_fingerprint", None)
            if action not in ("ui_suspend","ui_stop") and (
                    type(ready) is not bool or type(error) is not str
                    or type(score_revision) is not int
                    or type(score_fingerprint) is not str):
                raise ValueError("UI control requires source-bound renderer readiness")
            current = self.read_models.control_snapshot()
            if action == "ui_review_previous":
                # The dialog retains a snapshot only to identify the
                # source that was offered. Python selects the actual
                # previous step from the current lesson, never the
                # outdated step number on the screen.
                context_revision = kwargs.pop("context_revision", None)
                context_fingerprint = kwargs.pop("context_fingerprint", None)
                if (type(context_revision) is not int
                        or type(context_fingerprint) is not str
                        or context_revision != current.get("revision")
                        or context_fingerprint != current.get("piece_fingerprint")):
                    raise ValueError("Resume prompt belongs to an obsolete lesson")
            if action not in ("ui_suspend","ui_stop") and ready and (
                    score_revision != current.get("revision")
                    or score_fingerprint != current.get("piece_fingerprint")):
                raise ValueError("Displayed score belongs to an earlier source revision")
            resolved, options = resolve_ui_intent(
                action, current, score_ready=bool(ready), score_error=error)
            if resolved is None:
                return project_command_outcome(None)
            action = resolved
            kwargs.update(options)
        with self.session_commands.reason(action):
            before = {"fingerprint": self.source_identity.fingerprint,
                      "stage_key": self.source_identity.plan.identity if self.source_identity.plan else None,
                      "bpm": self.source_identity.plan.bpm if self.source_identity.plan else None, "mode": self.playback_session.mode}
            effect = self.session_commands.active
            route = ControlDispatcher.route(action)
            if self.source_identity.plan is not None and route in ("listening", "learning", "transport", "stage") and not (action in ("start","restart") and (self.attempt.settlement_failed or self.attempt_settlement.pending_rolling is not None)):
                change = (prepare_stage_change(self.source_identity.plan, action, kwargs, warmup=self.source_identity.warmup)
                          if route == "stage" else None)
                effect = self.teaching_decisions.prepare("manual", manual=change,
                    action=action, from_beat=kwargs.get("from_beat",kwargs.get("start_beat")), store=False, values=kwargs)
            with self.session_commands.executing(effect):
                result = self._dispatch_control(action, route, **kwargs)
                self.read_models.prepare_score_presentation()
                if action not in ("score_ready", "demo_ready", "reset_path"):
                    self.measurement.event("manual_action", {"action": action,
                        "fingerprint": before["fingerprint"] or None,
                        "parameters": kwargs, "before": before,
                        "after": {"fingerprint": self.source_identity.fingerprint,
                                  "stage_key": self.source_identity.plan.identity if self.source_identity.plan else None,
                                  "bpm": self.source_identity.plan.bpm if self.source_identity.plan else None, "mode": self.playback_session.mode}})
                return project_command_outcome(action)

    def _dispatch_control(self, action: str, route: str, **kwargs) -> None:
        """Dispatch within the existing outer command transaction and lock."""
        self.exposure_workflows.apply_listen_failure()
        if route == "calibration":
            return self.calibration_action(action)
        if route == "device_range":
            if action == "midi_range_cancel":
                self.midi_key_shortcuts.cancel_capture()
            else:
                if not self.midi.connected:
                    raise ValueError("Connect a MIDI piano before setting its key range")
                if self.playback_session.running and not self.visual_transport.paused:
                    self.timed_playback.pause()
                self.midi_key_shortcuts.begin_capture(self.midi.device)
            return
        if route == "reset":
            return self.history_management.reset_current_path(
                fingerprint=kwargs.get("fingerprint"),
                confirm=kwargs.get("confirm") is True)
        if route == "acknowledgement":
            return self.transport_commands.control_acknowledgement(action, kwargs)
        if route == "listening":
            return self.learning_commands.control_listening(action, kwargs)
        if route == "learning":
            return self.learning_commands.control_learning(action, kwargs)
        if route == "transport":
            return self.transport_commands.control_transport(action, kwargs)
        return self.learning_commands.change_stage(action, kwargs)


    def apply(self, event: PracticeEvent) -> dict | int | None:
        """Commit one typed action under the existing application lock.

        Heavy source import and fingering inference run under the separate
        source-mutation guard without holding this lock. Only prepared
        installation, attested physical receipts and ordinary state changes
        reach this synchronous transaction boundary.
        """
        with self.lock:
            if isinstance(event, TimedStartRequested):
                return self.timed_playback.start(**event.arguments)
            if isinstance(event, UserCommand):
                return self._apply_command(event.action, **event.parameters)
            if isinstance(event, PhysicalMidi):
                return self.midi_application_input._deliver_message(
                    event.message, received_at=event.received_at,
                    corrected_at=event.corrected_at, deferred=event.deferred)
            if isinstance(event, ClockAdvanced):
                return self._advance_tick()
            if isinstance(event, MidiShortcut):
                effect = event.effect
                if effect.completed_range is not None:
                    self.settings_workflows.record_midi_key_range(
                        self.midi.device, effect.completed_range,
                        pause_current=self.timed_playback.pause)
                if effect.action:
                    return self._apply_command(effect.action)
                return None
            if isinstance(event, PresentationRequired):
                return self.transport_commands.enable_presentation()
            if isinstance(event, PlaybackReserved):
                return self.transport_commands.reserve_physical(**event.receipt)
            if isinstance(event, PlaybackPresented):
                return self.transport_commands.present_physical(**event.receipt)
            if isinstance(event, PlaybackWithdrawn):
                return self.transport_commands.withdraw_physical(**event.receipt)
            if isinstance(event, PlaybackFailed):
                return self.transport_commands.fail_physical(**event.failure)
            if isinstance(event, SourceCommitted):
                resumed = self.source_workflows.install(
                    event.prepared, warmup=event.warmup)
                if resumed is not None:
                    self.lesson_execution.flow_open(resumed=resumed)
                if event.opened_identifier is not None:
                    self.source_workflows.mark_library_opened(
                        event.opened_identifier, warmup=event.warmup)
                return resumed
            if isinstance(event, FingeringCorrectionCommitted):
                return self.source_workflows.install_fingering_correction(
                    event.corrected)
            if isinstance(event, SettingsChanged):
                return self.settings_workflows.update(
                    event.changes, pause_current=self.timed_playback.pause)
            if isinstance(event, DeviceSelected):
                return self.midi_application_input.connect(event.name)
            if isinstance(event, PreloadReady):
                return self.score_preload.acknowledge_preloaded_stage(
                    stage_key=event.stage_key, revision=event.revision)
            if isinstance(event, PreloadFailed):
                return self.score_preload.report_preload_failure(
                    fingerprint=event.fingerprint,step_number=event.step_number,
                    revision=event.revision,error=event.error)
            if isinstance(event, CalibrationRequested):
                return self.calibration_action(event.action)
            if isinstance(event, HardwareRequested):
                return self.device_workflows.hardware_action(event.action)
            if isinstance(event, HistoryExported):
                return self.history_management.export(
                    event.path, include_detail=event.include_detail)
            if isinstance(event, PieceHistoryDeleted):
                return self.history_management.delete_piece(
                    event.fingerprint, confirm=event.confirm)
            if isinstance(event, LearnerHistoryDeleted):
                return self.history_management.delete_learner(
                    confirm=event.confirm)
            if isinstance(event, SessionClosed):
                return self.lifecycle.shutdown(
                    midi=self.midi, progress=self.progress,
                    receive=self.midi_application_input.receive)
            raise TypeError("Unsupported practice session event")

    def control(self, action: str, **kwargs) -> dict:
        return self.apply(UserCommand(action, kwargs))

    def on_midi(self, message, *, received_at=None, corrected_at=None,
                deferred=False) -> None:
        self.apply(PhysicalMidi(message, received_at, corrected_at, deferred))

    def on_shortcut(self, effect) -> None:
        self.apply(MidiShortcut(effect))

    def advance(self) -> int:
        began = time.perf_counter()
        try:
            return self.apply(ClockAdvanced())
        finally:
            self.runtime_timings.tick_ms.append(
                (time.perf_counter()-began)*1000.0)

    def _advance_tick(self) -> int:
        # Same native transaction: settle musical handoffs, replay MIDI
        # using the new take identity, then publish a single final state.
        self.timeline.settle_transitions()
        while self.midi_ingress.deferred:
            message, received_at, corrected_at, _transport = self.midi_ingress.deferred.popleft()
            self.midi_application_input._deliver_message(
                message, received_at=received_at,
                corrected_at=corrected_at, deferred=True)
        self.timeline.publish_settled()
        if self.source_identity.plan is None or self.visual_transport.paused:
            return 250
        if (self.playback_session.running
                or self.visual_transport.preview_loop_pending
                or self.visual_transport.preparation_pending
                or self.attempt_settlement.pending_result is not None
                or self.visual_transport.pending_rewind is not None
                or self.playback_session.mode == "listen"):
            return 20
        return 100
