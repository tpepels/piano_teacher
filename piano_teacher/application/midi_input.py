"""The MIDI input domain: one owner for the keyboard and its input facts.

Internals: midi (MidiConnection: device, port, scan), ingress (MidiIngress:
timestamped routing, deferred keys, resume grading gate), shortcuts
(MidiKeyShortcuts: configured end keys and key-range capture),
calibration (MidiTapCalibration) and live (LiveInputView).

Other modules read through the read-only properties below and change
state only through these named operations; the internals are never
referenced outside the domain's own modules.
"""
from __future__ import annotations


class MidiInput:
    def __init__(self, *, midi, shortcuts, calibration, live):
        self._midi = midi
        self._ingress = None
        self._shortcuts = shortcuts
        self._calibration = calibration
        self._live = live

    def attach_ingress(self, ingress) -> None:
        """Bind once during composition."""
        if self._ingress is not None:
            raise RuntimeError("ingress is already attached")
        self._ingress = ingress

    # --- midi

    @property
    def connected(self):
        return self._midi.connected

    @property
    def device(self):
        return self._midi.device

    @property
    def device_generation(self):
        return self._midi.generation

    @property
    def device_closed(self):
        return self._midi.closed

    def diagnostics_action(self, *args, **kwargs):
        return self._midi.diagnostics_action(*args, **kwargs)

    def disconnected(self, *args, **kwargs):
        return self._midi.disconnected(*args, **kwargs)

    @property
    def enabled(self):
        return self._midi.enabled

    @property
    def input_at(self):
        return self._midi.input_at

    @property
    def input_count(self):
        return self._midi.input_count

    @property
    def input_note(self):
        return self._midi.input_note

    def observe_midi(self, *args, **kwargs):
        return self._midi.observe(*args, **kwargs)

    def restore_preferred_device(self, *args, **kwargs):
        return self._midi.restore_preferred(*args, **kwargs)

    def scan_devices(self, *args, **kwargs):
        return self._midi.scan(*args, **kwargs)

    def scan_due(self, *args, **kwargs):
        return self._midi.scan_due(*args, **kwargs)

    def selecting_device(self, *args, **kwargs):
        return self._midi.selecting(*args, **kwargs)

    # --- midi_ingress

    def clear_resume_gate(self, *args, **kwargs):
        return self._ingress.clear_resume_gate(*args, **kwargs)

    @property
    def deferred_midi(self):
        return self._ingress.deferred

    def dispatch_midi(self, *args, **kwargs):
        return self._ingress.dispatch(*args, **kwargs)

    @property
    def resume_grading_after(self):
        return self._ingress.resume_grading_after

    # --- midi_key_shortcuts

    def begin_key_range_capture(self, *args, **kwargs):
        return self._shortcuts.begin_capture(*args, **kwargs)

    def cancel_key_range_capture(self, *args, **kwargs):
        return self._shortcuts.cancel_capture(*args, **kwargs)

    def configure_shortcuts(self, *args, **kwargs):
        return self._shortcuts.configure(*args, **kwargs)

    def discard_stale_release(self, *args, **kwargs):
        return self._shortcuts.discard_stale_release(*args, **kwargs)

    def key_range_status(self, *args, **kwargs):
        return self._shortcuts.status(*args, **kwargs)

    # --- shortcuts

    # --- midi_calibration

    def advance_calibration(self, *args, **kwargs):
        return self._calibration.advance(*args, **kwargs)

    def calibration_snapshot(self, *args, **kwargs):
        return self._calibration.snapshot(*args, **kwargs)

    def cancel_calibration(self, *args, **kwargs):
        return self._calibration.cancel(*args, **kwargs)

    def reset_calibration(self, *args, **kwargs):
        return self._calibration.reset(*args, **kwargs)

    def start_calibration(self, *args, **kwargs):
        return self._calibration.start(*args, **kwargs)

    # --- calibration

    # --- live_input

    def observe_physical_keys(self, message, *, received_at):
        self._live.observe_physical(message, received_at=received_at)

    def clear_live_device(self, *args, **kwargs):
        return self._live.clear_device(*args, **kwargs)

    def live_input_snapshot(self, *args, **kwargs):
        return self._live.snapshot(*args, **kwargs)

    def reset_live_input(self, *args, **kwargs):
        return self._live.reset_attempt(*args, **kwargs)

    # --- grading gate used by the transport domain
    def authorize_grading_after(self, *args, **kwargs):
        return self._ingress.authorize_grading_after(*args, **kwargs)
