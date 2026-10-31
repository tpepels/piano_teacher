"""Best-effort loopback MIDI note-on notifications for the Godot renderer.

No scoring, no transport control and no additional process. A UDP datagram
per actual note-on avoids waiting for the full /state JSON/poll cycle.
The existing /state event queue remains the reliable fallback.
"""
from __future__ import annotations

import json
import socket


class MidiVisualPublisher:
    def __init__(self) -> None:
        self.port = 0
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setblocking(False)

    def subscribe(self, port: int) -> None:
        if type(port) is not int or not 1024 <= port <= 65535:
            raise ValueError("Local MIDI feedback listener port must be between 1024 and 65535")
        self.port = port

    def publish(self, event: dict) -> None:
        if not self.port:
            return
        if event.get("status") not in ("on_time", "early", "late", "unexpected"):
            return
        message = {
            "sequence": event.get("sequence"),
            "transport_id": event.get("transport_id"),
            "status": event.get("status"),
            "pitch": event.get("pitch"),
            "source_id": event.get("source_id", ""),
            "reference_source_id": event.get("reference_source_id", ""),
        }
        try:
            self.socket.sendto(json.dumps(message, separators=(",", ":")).encode("utf-8"),
                               ("127.0.0.1", self.port))
        except (OSError, ValueError):
            # Visual feedback is nonessential. Never block physical MIDI.
            pass

    def close(self) -> None:
        self.socket.close()
