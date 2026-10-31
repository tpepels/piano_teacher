"""In-process Godot/Python commands and bounded MIDI event retrieval.

The Godot GDExtension calls request() on a worker thread. Responses
contain status and compact JSON or binary audio bytes.
"""
from __future__ import annotations

import json
import os
import time
import traceback
from urllib.parse import parse_qs

from .server import PracticeEngine
from .live_event_ring import LiveEventRing


class EngineCommands:
    def __init__(self, *, engine: PracticeEngine | None = None):
        self.engine = engine if engine is not None else PracticeEngine()
        self.owned = engine is None

    @staticmethod
    def _reply(status: int, value: object) -> tuple[int, bytes]:
        return status, json.dumps(value, separators=(",", ":")).encode("utf-8")

    def request(self, method: str, target: str, body: str = "") -> tuple[int, bytes]:
        began = time.perf_counter()
        try:
            route, _, query_string = target.partition("?")
            if method == "GET":
                return self._get(route, parse_qs(query_string))
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
        finally:
            if os.environ.get("PIANO_TEACHER_TIMING_DIAGNOSTICS") == "1":
                elapsed_ms = (time.perf_counter() - began) * 1000.0
                if elapsed_ms >= 24.0:
                    print("INPROCESS_COMMAND_SLOW:", method, target.partition("?")[0],
                          round(elapsed_ms, 2), "ms", flush=True)

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
        if path == "/midi/live":
            since = int(query.get("since", ["0"])[0])
            if since < 0:
                raise ValueError("MIDI event sequence must be nonnegative")
            return self._reply(200, self.drain_midi_events(since))
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
        # Presentation cannot mutate the recorder or assessment clock.
        with self.engine.lock:
            return self.engine.live_events.after(since)

    def close(self) -> None:
        if not self.owned:
            return
        self.engine.connect("")
        self.engine.db.close()
