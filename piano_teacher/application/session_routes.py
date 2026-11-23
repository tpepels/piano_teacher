"""The one table of which workflow handles each session event and command.

PracticeSession serializes events and CommandRouter resolves learner
commands; neither knows the workflows. Adding an event or command family
means adding its type here and one entry below.
"""
from __future__ import annotations

from .session_events import (
    UserCommand, ClockAdvanced, MidiShortcut, PhysicalMidi,
    PlaybackReserved, PlaybackPresented, PlaybackWithdrawn, PlaybackFailed,
    SourceCommitted, FingeringCorrectionCommitted, SettingsChanged,
    DeviceSelected, MidiPortsRequested, PreloadReady, PreloadFailed,
    HardwareRequested, HistoryExported, PieceHistoryDeleted,
    LearnerHistoryDeleted, SessionClosed,
)


def command_routes(*, device_workflows, settings_workflows, midi_input,
                   transport, pause_resume, history_management,
                   transport_commands, playback_authorization,
                   learning_commands, navigation):
    """Route family -> handler(action, kwargs, effect)."""
    def calibration(action, kwargs, effect):
        changes = device_workflows.calibrate(action, stop_reason=action)
        if changes is not None:
            settings_workflows.update(changes, pause_current=pause_resume.pause)

    def device_range(action, kwargs, effect):
        if action == "midi_range_cancel":
            midi_input.cancel_key_range_capture()
            return
        if not midi_input.connected:
            raise ValueError("Connect a MIDI piano before setting its key range")
        if transport.running and not transport.paused:
            pause_resume.pause()
        midi_input.begin_key_range_capture(midi_input.device)

    return {
        "calibration": calibration,
        "device_range": device_range,
        "reset": lambda action, kwargs, effect: history_management.reset_current_path(
            fingerprint=kwargs.get("fingerprint"), confirm=kwargs.get("confirm") is True),
        "acknowledgement": lambda action, kwargs, effect:
            playback_authorization.control_acknowledgement(action, kwargs, reason=action),
        "listening": lambda action, kwargs, effect:
            learning_commands.control_listening(action, kwargs, effect=effect),
        "learning": lambda action, kwargs, effect:
            learning_commands.control_learning(action, kwargs, effect=effect),
        "transport": lambda action, kwargs, effect:
            transport_commands.control_transport(action, kwargs, effect=effect),
        "stage": lambda action, kwargs, effect:
            navigation.change_stage(action, kwargs, effect=effect),
    }


def event_handlers(*, commands, tick, epoch, midi_input, midi_delivery,
                   midi_device, midi_callback,
                   settings_workflows, pause_resume, playback_authorization,
                   source_installation, library_opening, lesson, course, score_preload,
                   device_workflows, history_management, history_reads,
                   lifecycle):
    """Event type -> handler(event)."""
    def physical(event):
        if (event.arrival is not None and not epoch.admits(
                event.arrival, event.received_at, event.corrected_at)):
            # Stale keys may update hardware observation/release hygiene,
            # but never current-take grading, calibration or shortcuts.
            # A late release must not leave a shortcut permanently
            # suppressed after Stop/source replacement.
            if event.arrival.device == midi_input.device:
                midi_input.discard_stale_release(event.message)
                midi_input.observe_midi(event.message, now=event.received_at)
            return None
        return midi_delivery.deliver(
            event.message, received_at=event.received_at,
            corrected_at=event.corrected_at, deferred=event.deferred)

    def shortcut(event):
        effect = event.effect
        if effect.completed_range is not None:
            settings_workflows.record_midi_key_range(
                midi_input.device, effect.completed_range,
                pause_current=pause_resume.pause)
        return commands.apply(effect.action) if effect.action else None

    def source(event):
        resumed = source_installation.install(event.prepared, warmup=event.warmup)
        lesson.forget_source_decisions()
        if resumed is not None:
            course.flow_open(resumed=resumed)
        if event.opened_identifier is not None:
            library_opening.mark_opened(
                event.opened_identifier, warmup=event.warmup)
        return resumed

    return {
        UserCommand: lambda e: commands.apply(e.action, **e.parameters),
        PhysicalMidi: physical,
        ClockAdvanced: lambda e: tick.advance(),
        MidiShortcut: shortcut,
        PlaybackReserved: lambda e: playback_authorization.reserve_physical(**e.receipt),
        PlaybackPresented: lambda e: playback_authorization.present_physical(**e.receipt),
        PlaybackWithdrawn: lambda e: playback_authorization.withdraw_physical(**e.receipt),
        PlaybackFailed: lambda e: playback_authorization.fail_physical(**e.failure),
        SourceCommitted: source,
        FingeringCorrectionCommitted: lambda e:
            source_installation.install_fingering_correction(e.corrected),
        SettingsChanged: lambda e: settings_workflows.update(
            e.changes, pause_current=pause_resume.pause),
        MidiPortsRequested: lambda e: midi_device.ports(),
        DeviceSelected: lambda e: midi_device.connect(e.name),
        PreloadReady: lambda e: score_preload.acknowledge_preloaded_stage(
            stage_key=e.stage_key, revision=e.revision),
        PreloadFailed: lambda e: score_preload.report_preload_failure(
            fingerprint=e.fingerprint, step_number=e.step_number,
            revision=e.revision, error=e.error),
        HardwareRequested: lambda e: device_workflows.hardware_action(e.action),
        HistoryExported: lambda e: history_reads.export(
            e.path, include_detail=e.include_detail),
        PieceHistoryDeleted: lambda e: history_management.delete_piece(
            e.fingerprint, confirm=e.confirm),
        LearnerHistoryDeleted: lambda e: history_management.delete_learner(
            confirm=e.confirm),
        SessionClosed: lambda e: lifecycle.shutdown(
            receive=midi_callback.receive),
    }
