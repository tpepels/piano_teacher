"""Single serialized application entrypoint for commands, MIDI and ticks.

The native worker and physical MIDI callback share the existing RLock and
the same active musical source. Lesson/transport/assessment owners retain
their decisions; the session sequences their effects and publications.
"""
from __future__ import annotations
from collections import deque
import time
from .control_projection import UI_INTENTS, resolve_ui_intent, project_command_outcome
from .stage_change import prepare_stage_change


from .session_events import (
    UserCommand,
    ClockAdvanced,
    ImmediateTransition,
    MidiShortcut,
    PhysicalMidi,
    MidiArrival,
    PlaybackReserved,
    PlaybackPresented,
    PlaybackWithdrawn,
    PlaybackFailed,
    SourceCommitted,
    FingeringCorrectionCommitted,
    SettingsChanged,
    DeviceSelected,
    MidiPortsRequested,
    PreloadReady,
    PreloadFailed,
    HardwareRequested,
    HistoryExported,
    PieceHistoryDeleted,
    LearnerHistoryDeleted,
    SessionClosed,
    PracticeEvent,
)

# User-command dispatch belongs to the same serialized session that
# validates the current state. Unknown action names remain delegated to
# the lesson stage validator; no second application router is constructed.
_COMMAND_ROUTES = {
    **dict.fromkeys(("calibration_start", "calibration_cancel",
                     "calibration_apply", "calibration_reset"), "calibration"),
    **dict.fromkeys(("midi_range_start", "midi_range_cancel"), "device_range"),
    "reset_path": "reset",
    **dict.fromkeys(("score_ready", "demo_ready"), "acknowledgement"),
    **dict.fromkeys(("listen", "perform", "practice_weak", "review_retry", "seek"), "listening"),
    **dict.fromkeys(("learn_next", "skip_stage", "place_original",
                     "revisit_trouble", "learn", "learn_retry",
                     "open_at", "hints"), "learning"),
    **dict.fromkeys(("practice", "stop", "start", "restart", "pause", "resume"), "transport"),
}


class PracticeSession:
    def __init__(self, *, take, device_workflows, exposure_workflows,
                          history_management, learning_commands, lock,
                          measurement, midi_input, transport, read_models,
                          settings_workflows, lesson, timed_playback,
                          transport_commands, timeline, midi_application_input,
                          runtime_timings, source_workflows, lesson_execution,
                          score_preload, lifecycle, notices, clock):
        self.take = take
        self.device_workflows = device_workflows
        self.exposure_workflows = exposure_workflows
        self.history_management = history_management
        self.learning_commands = learning_commands
        self.lock = lock
        self.measurement = measurement
        self.midi_input = midi_input
        self.transport = transport
        self.read_models = read_models
        self.settings_workflows = settings_workflows
        self.lesson = lesson
        self.timed_playback = timed_playback
        self.transport_commands = transport_commands
        self.timeline = timeline
        self.midi_application_input = midi_application_input
        self.runtime_timings = runtime_timings
        self.source_workflows = source_workflows
        self.lesson_execution = lesson_execution
        self.score_preload = score_preload
        self.lifecycle = lifecycle
        # One atomically published immutable epoch. Physical callbacks can
        # read it without waiting for the lock, then validate the original
        # epoch when their event is finally executed under that same lock.
        self._committed_midi_arrival = self._current_midi_arrival()
        self._event_depth = 0
        self.notices = notices
        self.clock = clock

    def calibration_action(self, action: str) -> None:
        changes = self.device_workflows.calibrate(
            action, stop_reason=action)
        if changes is not None:
            self.settings_workflows.update(
                changes, pause_current=self.timed_playback.pause)

    def _apply_command(self, action: str, **kwargs) -> dict:
        # Explicit Stop is a one-way cancellation, including while Godot
        # is replaying a queued Stop after a delayed command acknowledgement.
        # It must not require a healthy score/read-model projection or an
        # unrelated curriculum decision to invalidate an active take.
        if action == "ui_stop":
            action = "stop"
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
        before = {"fingerprint": self.lesson.fingerprint,
                  "stage_key": self.lesson.plan.identity if self.lesson.plan else None,
                  "bpm": self.lesson.plan.bpm if self.lesson.plan else None, "mode": self.transport.mode}
        effect = None
        route = _COMMAND_ROUTES.get(action, "stage")
        # Stop/Pause/Resume only mutate transport state. The selected lesson
        # never consumes their teaching effect, so they cannot be blocked by
        # curriculum generators, learner-history reads or stale evidence.
        needs_teaching = action not in ("stop", "pause", "resume")
        if (needs_teaching and self.lesson.plan is not None
                and route in ("listening", "learning", "transport", "stage")
                and not (action in ("start","restart")
                         and (self.take.settlement_failed
                              or self.take.pending_rolling is not None))):
            change = (prepare_stage_change(self.lesson.plan, action, kwargs, warmup=self.lesson.warmup)
                      if route == "stage" else None)
            effect = self.lesson.prepare_decision("manual", manual=change,
                action=action, from_beat=kwargs.get("from_beat",kwargs.get("start_beat")), store=False, values=kwargs)
        self._dispatch_control(action, route, effect=effect, **kwargs)
        self.read_models.prepare_score_presentation()
        if action not in ("score_ready", "demo_ready", "reset_path"):
            self.measurement.event("manual_action", {"action": action,
                "fingerprint": before["fingerprint"] or None,
                "parameters": kwargs, "before": before,
                "after": {"fingerprint": self.lesson.fingerprint,
                          "stage_key": self.lesson.plan.identity if self.lesson.plan else None,
                          "bpm": self.lesson.plan.bpm if self.lesson.plan else None, "mode": self.transport.mode}})
        return project_command_outcome(action)

    def _dispatch_control(self, action: str, route: str, *, effect=None, **kwargs) -> None:
        """Dispatch within the existing outer command transaction and lock."""
        self.exposure_workflows.apply_listen_failure()
        if route == "calibration":
            return self.calibration_action(action)
        if route == "device_range":
            if action == "midi_range_cancel":
                self.midi_input.cancel_key_range_capture()
            else:
                if not self.midi_input.connected:
                    raise ValueError("Connect a MIDI piano before setting its key range")
                if self.transport.running and not self.transport.paused:
                    self.timed_playback.pause()
                self.midi_input.begin_key_range_capture(self.midi_input.device)
            return
        if route == "reset":
            return self.history_management.reset_current_path(
                fingerprint=kwargs.get("fingerprint"),
                confirm=kwargs.get("confirm") is True)
        if route == "acknowledgement":
            return self.transport_commands.control_acknowledgement(action, kwargs,reason=action)
        if route == "listening":
            return self.learning_commands.control_listening(action, kwargs, effect=effect)
        if route == "learning":
            return self.learning_commands.control_learning(action, kwargs, effect=effect)
        if route == "transport":
            return self.transport_commands.control_transport(action, kwargs, effect=effect)
        return self.learning_commands.change_stage(action, kwargs, effect=effect)


    def _current_midi_arrival(self) -> MidiArrival:
        """Current accepted epoch; caller holds the existing session lock."""
        plan = self.lesson.plan
        return MidiArrival(
            self.midi_input.device, self.lesson.fingerprint,
            self.lesson.revision,
            plan.identity if plan is not None else "",
            plan.hand if plan is not None else "both",
            self.transport.transport_id,
            self.take.cancellation_generation,
            bool(self.transport.auto))

    def midi_arrival(self) -> MidiArrival:
        """Lock-free immutable snapshot for the physical callback timestamp."""
        return self._committed_midi_arrival

    def _same_midi_epoch(self, arrival: MidiArrival, received_at: float,
                         corrected_at: float | None = None) -> bool:
        current = self._current_midi_arrival()
        # Stop, source replacement, new engraved revision, a new lesson
        # stage/hand, or explicit take cancellation invalidate queued keys.
        if (arrival.device != current.device or
                arrival.fingerprint != current.fingerprint or
                arrival.revision != current.revision or
                arrival.stage_key != current.stage_key or
                arrival.hand != current.hand or
                arrival.cancellation_generation != current.cancellation_generation):
            return False
        if arrival.transport_id == current.transport_id:
            return True
        # A different take epoch may accept a late-arriving hardware key
        # only during a same-source automatic repeat, after the new
        # physical start. Manual restart/Stop never inherits old keys.
        if (not arrival.automatic or not current.automatic or
                not self.transport.running or self.transport.paused):
            return False
        if received_at is None:
            # An unspecified hardware timestamp can never authorize a
            # previous take's queued key in a newer transport epoch.
            return False
        adjusted_at = self.midi_application_input.corrected_time(
            received_at, corrected_at)
        return adjusted_at >= self.transport.run_at

    def apply(self, event: PracticeEvent) -> dict | int | None:
        """Serialize the event and atomically publish its committed MIDI epoch.

        Callback identity is sampled before acquiring the lock; command,
        score adoption, cancellation and hardware input commit under it.
        """
        with self.lock:
            self._event_depth += 1
            try:
                return self._dispatch(event)
            finally:
                self._event_depth -= 1
                # MIDI shortcuts can re-enter this same RLock through a
                # second typed event. Nested events cannot publish their
                # intermediate callback epoch before the parent commits.
                if self._event_depth == 0:
                    self._committed_midi_arrival = self._current_midi_arrival()

    def _dispatch(self, event: PracticeEvent) -> dict | int | None:
        """Execute a previously locked, typed session action."""
        if isinstance(event, UserCommand):
            return self._apply_command(event.action, **event.parameters)
        if isinstance(event, PhysicalMidi):
            if (event.arrival is not None and
                    not self._same_midi_epoch(
                        event.arrival, event.received_at,
                        event.corrected_at)):
                # Stale keys may update hardware observation/release hygiene,
                # but never current-take grading, calibration or shortcuts.
                # A late release must not leave a shortcut permanently
                # suppressed after Stop/source replacement.
                if event.arrival.device == self.midi_input.device:
                    self.midi_input.discard_stale_release(event.message)
                    self.midi_input.observe_midi(event.message, now=event.received_at)
                return None
            return self.midi_application_input._deliver_message(
                event.message, received_at=event.received_at,
                corrected_at=event.corrected_at, deferred=event.deferred)
        if isinstance(event, ClockAdvanced):
            return self._advance_tick()
        if isinstance(event, MidiShortcut):
            effect = event.effect
            if effect.completed_range is not None:
                self.settings_workflows.record_midi_key_range(
                    self.midi_input.device, effect.completed_range,
                    pause_current=self.timed_playback.pause)
            if effect.action:
                return self._apply_command(effect.action)
            return None
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
            self.lesson.forget_source_decisions()
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
        if isinstance(event, MidiPortsRequested):
            return self.midi_application_input.ports()
        if isinstance(event, DeviceSelected):
            return self.midi_application_input.connect(event.name)
        if isinstance(event, PreloadReady):
            return self.score_preload.acknowledge_preloaded_stage(
                stage_key=event.stage_key, revision=event.revision)
        if isinstance(event, PreloadFailed):
            return self.score_preload.report_preload_failure(
                fingerprint=event.fingerprint,step_number=event.step_number,
                revision=event.revision,error=event.error)
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
                receive=self.midi_application_input.receive)
        raise TypeError("Unsupported practice session event")


    def control(self, action: str, **kwargs) -> dict:
        return self.apply(UserCommand(action, kwargs))

    def on_midi(self, message, *, received_at=None, corrected_at=None,
                deferred=False, arrival=None) -> None:
        # Direct/headless adapters default to the most recently committed
        # epoch; physical callback adapters supply the one sampled at arrival.
        sampled = (self.midi_application_input.clock()
                   if received_at is None else received_at)
        self.apply(PhysicalMidi(message, sampled, corrected_at, deferred,
                                self.midi_arrival() if arrival is None else arrival))

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
        immediate = deque((ImmediateTransition(),))
        transitions = 0
        try:
            while immediate:
                immediate.popleft()
                if transitions >= 17:
                    raise RuntimeError(
                        "Practice transitions exceeded the bounded same-tick handoff")
                transitions += 1
                if self.timeline.update_transition():
                    immediate.append(ImmediateTransition())
        except Exception:
            self.transport.freeze_after_fault(self.clock())
            # A failing transition bypasses the normal publish_settled()
            # tail. Reconcile the original physical take's current paused
            # status without reentering assessment or successor effects.
            self.timeline.publish_failed_transition()
            self.notices.fault("Could not save or finish the practice transition",
                "Check storage or the reported error, then Resume to retry this same take.")
            raise
        while self.midi_input.deferred_midi:
            item = self.midi_input.deferred_midi.popleft()
            # The original ingress key is part of the immutable queued note.
            # Use the same epoch gate as an in-flight physical callback.
            if not self._same_midi_epoch(
                    item.arrival, item.received_at, item.corrected_at):
                continue
            self.midi_application_input._deliver_message(
                item.message, received_at=item.received_at,
                corrected_at=item.corrected_at, deferred=True)
        self.timeline.publish_settled()
        if self.lesson.plan is None or self.transport.paused:
            return 250
        if (self.transport.running
                or self.transport.preview_loop_pending
                or self.transport.preparation_pending
                or self.take.pending_result is not None
                or self.transport.pending_rewind is not None
                or self.transport.mode == "listen"):
            return 20
        return 100
