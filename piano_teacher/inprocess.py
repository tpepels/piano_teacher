"""In-process application command dispatcher.

This is the same user-facing contract as the previous HTTP routes, but
without URL clients, ports, sockets, HTTP headers, or another process.
The native Godot extension calls request() on a worker thread. Responses
are (status, bytes); audio is binary, other responses are compact JSON.
"""
from __future__ import annotations

import json
import traceback
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .server import PracticeEngine


class InMemoryVisualPublisher:
    """MIDI callback -> bounded in-process ring, no socket or serialization."""
    def __init__(self):
        from collections import deque
        self.events = deque(maxlen=128)

    def publish(self, event: dict) -> None:
        self.events.append(dict(event))

    def close(self) -> None:
        self.events.clear()


class EngineCommands:
    def __init__(self, *, engine: PracticeEngine | None = None):
        self.engine = engine if engine is not None else PracticeEngine(visual_publisher=InMemoryVisualPublisher())
        self.owned = engine is None

    @staticmethod
    def _reply(status: int, value: object) -> tuple[int, bytes]:
        return status, json.dumps(value, separators=(",", ":")).encode("utf-8")

    def request(self, method: str, target: str, body: str = "") -> tuple[int, bytes]:
        try:
            url = urlsplit(target)
            route = url.path
            if method == "GET":
                return self._get(route, parse_qs(url.query))
            if method == "POST":
                payload = json.loads(body) if body else {}
                if not isinstance(payload, dict):
                    raise ValueError("Command body must be a JSON object")
                return self._post(route, payload)
            return self._reply(405, {"error": "Unsupported command"})
        except (KeyError, ValueError, TypeError, RuntimeError) as exc:
            return self._reply(400, {"error": str(exc)})
        except Exception as exc:
            traceback.print_exc()
            return self._reply(500, {"error": f"Practice engine error: {exc}"})

    def _get(self, path: str, query: dict) -> tuple[int, bytes]:
        engine = self.engine
        commands = {
            "/state": "state",
            "/fingering": "fingering_status",
            "/library": "library_listing",
            "/library/health": "library_health_status",
            "/lesson": "lesson_overview",
            "/settings": "preferences",
            "/exercise/diagnostics": "exercise_diagnostics",
            "/diagnostics/hardware": "hardware_diagnostics",
            "/diagnostics/performance": "performance_diagnostics",
            "/score/model": "semantic_score",
        }
        if path == "/devices":
            return self._reply(200, {"devices": engine.ports()})
        if path in commands:
            return self._reply(200, getattr(engine, commands[path])())
        if path == "/score/layout":
            raw = query.get("native", ["1"])[0]
            if raw not in ("0", "1"):
                raise ValueError("native must be 0 or 1")
            return self._reply(200, engine.geometry(native_notes=raw == "1"))
        if path == "/demo.wav":
            return 200, engine.demo_audio(query.get("token", [""])[0]).read_bytes()
        if path == "/score.svg":
            return 200, engine.engraved(int(query.get("page", ["0"])[0])).encode("utf-8")
        if path == "/score.png":
            page = int(query.get("page", ["0"])[0])
            if "width" in query:
                return 200, engine.engraved_png(page, width=int(query["width"][0]))
            return 200, engine.engraved_png(page)
        return self._reply(404, {"error": f"Unknown command: {path}"})

    def _post(self, path: str, data: dict) -> tuple[int, bytes]:
        engine = self.engine
        if path == "/load":
            engine.load(data["path"])
        elif path == "/fingering":
            engine.correct_fingering(data["source_id"], data["finger"],
                                     fingerprint=data.get("fingerprint"))
        elif path == "/library/open":
            engine.load_library(data["id"])
        elif path == "/library/health":
            return self._reply(200, engine.start_library_health())
        elif path == "/settings":
            engine.set_preferences(**data)
        elif path == "/device":
            engine.connect(data.get("name", ""))
        elif path == "/diagnostics/hardware":
            return self._reply(200,
                               engine.hardware_diagnostics_action(data.get("action", "")))
        elif path == "/control":
            engine.control(**data)
        else:
            return self._reply(404, {"error": f"Unknown command: {path}"})
        return self._reply(200, engine.preferences() if path == "/settings" else engine.state())

    def drain_midi_events(self, since: int) -> list[dict]:
        # Events remain source- and transport-versioned. Never duplicate them
        # or let presentation mutate the recorder/assessment clock.
        # These events have already been classified synchronously in the MIDI
        # callback. A bounded ring does not depend on HTTP or UDP subscribers.
        with self.engine.lock:
            events = self.engine.midi_visual_publisher.events
            return [dict(event) for event in events
                    if int(event.get("sequence", 0)) > since]

    def close(self) -> None:
        if not self.owned:
            return
        self.engine.connect("")
        self.engine.db.close()
