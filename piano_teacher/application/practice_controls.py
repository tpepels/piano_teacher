"""Single locked user/native command boundary with typed owner routes.

Manual intent and evidence are recorded here; lesson and transport actions
are dispatched to their dedicated workflows, not decided a second time.
"""
from __future__ import annotations
from .control_dispatch import ControlDispatcher
from .stage_change import prepare_stage_change


class PracticeControls:
    def __init__(self, *,
                 attempt, attempt_settlement, device_workflows, exposure_workflows,
                 history_management, learning_commands, lock, measurement,
                 midi, midi_key_shortcuts, playback_session, read_models,
                 session_commands, settings_workflows, source_identity, teaching_decisions,
                 timed_playback, transport_commands, visual_transport):
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

    def calibration_action(self, action: str) -> None:
        changes = self.device_workflows.calibrate(
            action, stop_reason=self.session_commands.action_reason)
        if changes is not None:
            self.settings_workflows.update(
                changes, pause_current=self.timed_playback.pause)

    def control(self, action: str, **kwargs) -> None:
        with self.lock, self.session_commands.reason(action):
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
                return result

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

