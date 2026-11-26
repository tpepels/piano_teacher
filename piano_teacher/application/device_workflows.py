"""MIDI connection, hardware diagnostics and calibration use cases.

The application boundary keeps teaching interruption ordering and the lock.
This component owns device lifecycle effects and emits preference changes as
explicit values for the settings transaction to apply.
"""
from __future__ import annotations


class DeviceWorkflows:
    def __init__(self, *, midi_input, lifecycle, lesson, notices, transport,
                          library, clock):
        self.midi_input = midi_input

        self.lifecycle = lifecycle
        self.lesson = lesson
        self.notices = notices
        self.transport = transport
        self.library = library
        self.clock = clock

    def present(self, notice) -> None:
        if notice is None:
            return
        teaching = self.lesson.guided_controller
        if notice.connected is not None and teaching is not None:
            teaching.set_connected(
                notice.connected,
                now=(notice.sampled_at
                     if notice.sampled_at is not None else self.clock()))
        self.notices.publish(notice.feedback, notice.next_action)

    def disconnect(self, reason: str) -> None:
        with self.midi_input.disconnected(reason) as notice:
            self.midi_input.cancel_key_range_capture()
            self.midi_input.clear_live_device()
            teaching = self.lesson.guided_controller
            if self.transport.mode != "learn" or teaching is None:
                # A timed take cannot be graded without the piano. Free has
                # no take: it keeps the notes found and waits for the piano.
                self.lifecycle.stop(reason=reason)
            if teaching is not None:
                teaching.set_connected(False, now=self.clock())
        self.notices.publish(notice.feedback, notice.next_action)

    def scan(self):
        return self.midi_input.scan_devices()

    def handle_scan_error(self, scan) -> None:
        if scan.error is not None:
            self.notices.feedback = scan.feedback
            raise RuntimeError(self.notices.feedback) from scan.error

    def restore_preferred(self, names, *, callback, callback_factory=None) -> None:
        self.present(self.midi_input.restore_preferred_device(
            names, self.library.settings.get("midi_device", ""),
            callback=callback, callback_factory=callback_factory))

    def select(self, name: str, *, callback, callback_factory=None) -> None:
        if name == self.midi_input.device and self.midi_input.connected:
            return  # A repeated preference selection must not restart a take.
        try:
            with self.midi_input.selecting_device(name, callback=callback,
                    callback_factory=callback_factory) as selected:
                self.midi_input.cancel_key_range_capture()
                self.midi_input.clear_live_device()
                # Free keeps its target index, but no held keys or gesture
                # from the retired port survive the connection change.
                teaching = self.lesson.guided_controller
                if teaching is not None:
                    teaching.set_connected(False, now=self.clock())
                if self.transport.mode != "learn" or teaching is None:
                    self.lifecycle.stop(reason="device_changed")
        except RuntimeError as exc:
            self.notices.feedback = str(exc)
            raise
        self.present(selected.notice)

    def hardware_action(self, action: str) -> dict:
        return self.midi_input.diagnostics_action(
            action, running=self.transport.running)

    def calibrate(self, action: str, *, stop_reason: str) -> dict | None:
        if action == "calibration_start":
            if not self.midi_input.connected:
                raise ValueError("Connect the MIDI keyboard before calibrating")
            self.lifecycle.stop(reason=stop_reason)
            self.midi_input.start_calibration(self.clock())
            self.notices.feedback = "Tap one key with every click"
        elif action == "calibration_cancel":
            self.midi_input.cancel_calibration()
        elif action == "calibration_apply":
            self.midi_input.advance_calibration(self.clock())
            result = self.midi_input.calibration_snapshot(self.clock())["result"]
            if not result or not result.get("reliable"):
                raise ValueError("Finish a consistent calibration before applying it")
            return {"midi_offset_ms":max(0,min(250,result["estimate_ms"]))}
        elif action == "calibration_reset":
            self.midi_input.reset_calibration()
            return {"midi_offset_ms":0}
        else:
            raise ValueError("Unsupported calibration command")
        return None

    def connection_due(self) -> bool:
        return self.midi_input.scan_due(self.library.settings.get("midi_device", ""))
