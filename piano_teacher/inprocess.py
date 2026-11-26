"""Typed in-memory command dispatcher for the embedded Godot Python worker.

Operations are namespaced application intents, with one JSON payload and
one result code. This protocol has no methods, routes, URLs, HTTP status
codes, server, socket or separate transport clock.
"""
from __future__ import annotations

import json
import os
import time
import traceback

from .server import PracticeEngine

OK = 0
INVALID = 1
UNKNOWN = 2
FAILED = 3


class EngineCommands:
    READS = {
        "state.snapshot": "poll_state",
        "library.catalog": "library_listing",
        "library.health_status": "library_health_status",
        "lesson.overview": "lesson_overview",
        "settings.snapshot": "preferences",
        "learning.status": "learning_history_status",
        "performance.diagnostics": "performance_diagnostics",
        "score.semantic": "semantic_score",
    }

    def __init__(self, *, engine: PracticeEngine | None = None):
        self.engine = engine if engine is not None else PracticeEngine()
        self.owned = engine is None

    def tick(self) -> int:
        """The same native worker advances all musical deadlines."""
        return self.engine.advance_clock()

    @staticmethod
    def _reply(status: int, value: object) -> tuple[int, bytes]:
        return status, json.dumps(value, separators=(",", ":")).encode("utf-8")

    def request(self, operation: str, payload_json: str = "") -> tuple[int, bytes]:
        started = time.perf_counter()
        try:
            values = json.loads(payload_json) if payload_json else {}
            if not isinstance(values, dict):
                raise ValueError("Command payload must be a JSON object")
            engine = self.engine
            if operation == "learning.statistics":
                from .learning_statistics_query import validate_query
                return self._reply(OK, engine.learning_statistics(query=validate_query(values)))
            if operation == "state.snapshot" and values:
                engine.report_placement(values)
                return self._reply(OK, engine.poll_state())
            if operation in self.READS:
                if values:
                    raise ValueError(f"{operation} takes no input")
                return self._reply(OK, getattr(engine, self.READS[operation])())
            if operation == "feedback.events":
                acknowledged = values.get("acknowledged", 0)
                if type(acknowledged) is not int or acknowledged < 0:
                    raise ValueError("Feedback acknowledgement must be a nonnegative sequence")
                return self._reply(OK, self.drain_feedback_events(acknowledged))
            if operation == "midi.devices":
                return self._reply(OK, {"devices": engine.ports()})
            if operation == "score.bundle":
                if values:
                    raise ValueError("score.bundle takes no input")
                return self._reply(OK, engine.score_bundle())
            if operation == "score.native_layout":
                return self._reply(OK, engine.geometry())
            if operation == "playback.status":
                if values:
                    raise ValueError("playback.status takes no input")
                return self._reply(OK, engine.playback_status())
            if operation == "playback.failure":
                return self._reply(OK, engine.report_playback_failure(**values))
            if operation == "listen.audio":
                return OK, engine.demo_audio(values.get("token", "")).read_bytes()
            if operation == "learning.export":
                if set(values) - {"path", "include_detail"}:
                    raise ValueError("Unknown learning export input")
                path = values.get("path")
                include_detail = values.get("include_detail", False)
                if type(path) is not str or not path.strip() or "\x00" in path:
                    raise ValueError("Choose a local export file")
                if type(include_detail) is not bool:
                    raise ValueError("Include detail must be true or false")
                return self._reply(OK, engine.export_learning_history(
                    path, include_detail=include_detail))
            if operation in {"learning.delete_piece", "learning.delete_learner"}:
                allowed = {"confirm", "fingerprint"} if operation == "learning.delete_piece" else {"confirm"}
                if set(values) - allowed:
                    raise ValueError("Unknown learning deletion input")
                if values.get("confirm") is not True:
                    raise ValueError("Permanent history deletion requires confirmation")
                if operation == "learning.delete_piece":
                    fingerprint = values.get("fingerprint")
                    if type(fingerprint) is not str or not fingerprint.strip():
                        raise ValueError("Select a piece before deleting its history")
                    return self._reply(OK, engine.delete_piece_history(fingerprint, confirm=True))
                return self._reply(OK, engine.delete_learner_history(confirm=True))
            if operation == "fingering.correct":
                engine.correct_fingering(values["source_id"], values["finger"],
                                         fingerprint=values.get("fingerprint"))
            elif operation == "library.open":
                engine.load_library(values["id"])
            elif operation == "sight_reading.start":
                engine.start_sight_reading(values["level"], values["tempo"])
            elif operation == "library.health.start":
                return self._reply(OK, engine.start_library_health())
            elif operation == "settings.update":
                # Settings preferences must correspond to the same committed
                # action, not an interleaved MIDI shortcut/settings update.
                # Retain the existing *public* settings response schema.
                with engine.lock:
                    engine.set_preferences(**values)
                    return self._reply(OK, engine.preferences())
            elif operation == "midi.device.select":
                engine.connect(values.get("name", ""))
            elif operation == "hardware.action":
                return self._reply(OK, engine.hardware_diagnostics_action(
                    values.get("action", "")))
            elif operation == "practice.command":
                # One accepted input event must return its own committed
                # state. Hardware MIDI callbacks can arrive on another
                # native thread between control() and state(); without this
                # outer RLock the UI might acknowledge action A while showing
                # the state produced by a later MIDI action B.
                # Outcome remains separate from the versioned state schema.
                with engine.lock:
                    outcome = engine.control(**values)
                    state = engine.state()
                return self._reply(OK, {
                    "state": state, "outcome": outcome,
                })
            else:
                return self._reply(UNKNOWN, {"error": f"Unknown operation: {operation}"})
            return self._reply(
                OK, engine.state())
        except (KeyError, ValueError, TypeError, RuntimeError) as exc:
            return self._reply(INVALID, {"error": str(exc)})
        except Exception as exc:
            traceback.print_exc()
            return self._reply(FAILED, {"error": f"Practice engine error: {exc}"})
        finally:
            if os.environ.get("PIANO_TEACHER_TIMING_DIAGNOSTICS") == "1":
                elapsed_ms = (time.perf_counter() - started) * 1000.0
                if elapsed_ms >= 24:
                    print("INPROCESS_COMMAND_SLOW:", operation,
                          round(elapsed_ms, 2), "ms", flush=True)

    def drain_feedback_events(self, acknowledged: int) -> dict:
        """Acknowledge processed events and return every later one."""
        with self.engine.lock:
            return self.engine.feedback_events.after(acknowledged)

    def close(self) -> None:
        if not self.owned:
            return
        self.engine.close()
