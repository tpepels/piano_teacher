"""MIDI connection, hardware diagnostics and calibration use cases.

The application boundary keeps teaching interruption ordering and the lock.
This component owns device lifecycle effects and emits preference changes as
explicit values for the settings transaction to apply.
"""
from __future__ import annotations


class DeviceWorkflows:
    def __init__(self, *, midi, shortcuts, live_input, lifecycle,
                 guided_session, notices, playback_session, calibration,
                 library, clock):
        self.midi = midi
        self.shortcuts = shortcuts
        self.live_input = live_input
        self.lifecycle = lifecycle
        self.guided_session = guided_session
        self.notices = notices
        self.playback_session = playback_session
        self.calibration = calibration
        self.library = library
        self.clock = clock

    def present(self, notice) -> None:
        if notice is None:
            return
        teaching = self.guided_session.controller
        if notice.connected is not None and teaching is not None:
            teaching.set_connected(
                notice.connected,
                now=(notice.sampled_at
                     if notice.sampled_at is not None else self.clock()))
        self.notices.publish(notice.feedback, notice.next_action)

    def disconnect(self, reason: str) -> None:
        with self.midi.disconnected(reason) as notice:
            self.shortcuts.cancel_capture()
            self.live_input.clear_device()
            self.lifecycle.stop(reason=reason)
            teaching = self.guided_session.controller
            if teaching is not None:
                teaching.set_connected(False, now=self.clock())
        self.notices.publish(notice.feedback, notice.next_action)

    def scan(self):
        return self.midi.scan()

    def handle_scan_error(self, scan) -> None:
        if scan.error is not None:
            self.notices.feedback = scan.feedback
            raise RuntimeError(self.notices.feedback) from scan.error

    def restore_preferred(self, names, *, callback) -> None:
        self.present(self.midi.restore_preferred(
            names, self.library.settings.get("midi_device", ""),
            callback=callback))

    def select(self, name: str, *, callback) -> None:
        try:
            with self.midi.selecting(name, callback=callback) as selected:
                self.shortcuts.cancel_capture()
                self.live_input.clear_device()
                self.lifecycle.stop(reason="device_changed")
        except RuntimeError as exc:
            self.notices.feedback = str(exc)
            raise
        self.present(selected.notice)

    def hardware_action(self, action: str) -> dict:
        return self.midi.diagnostics_action(
            action, running=self.playback_session.running)

    def calibrate(self, action: str, *, stop_reason: str) -> dict | None:
        if action == "calibration_start":
            if not self.midi.connected:
                raise ValueError("Connect the MIDI keyboard before calibrating")
            self.lifecycle.stop(reason=stop_reason)
            self.calibration.start(self.clock())
            self.notices.feedback = "Tap one key per click through five continuous rounds"
        elif action == "calibration_cancel":
            self.calibration.cancel()
        elif action == "calibration_apply":
            self.calibration.advance(self.clock())
            result = self.calibration.snapshot(self.clock())["result"]
            if not result or not result.get("reliable"):
                raise ValueError("Finish a consistent calibration before applying it")
            return {"midi_offset_ms":max(0,min(250,result["estimate_ms"]))}
        elif action == "calibration_reset":
            self.calibration.reset()
            return {"midi_offset_ms":0}
        else:
            raise ValueError("Unsupported calibration command")
        return None

    def connection_due(self) -> bool:
        return self.midi.scan_due(self.library.settings.get("midi_device", ""))
