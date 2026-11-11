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
        "fingering.status": "fingering_status",
        "library.catalog": "library_listing",
        "library.health_status": "library_health_status",
        "lesson.overview": "lesson_overview",
        "settings.snapshot": "preferences",
        "learning.status": "learning_history_status",
        "exercise.diagnostics": "exercise_diagnostics",
        "hardware.diagnostics": "hardware_diagnostics",
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
                if set(values) - {"fingerprint"}:
                    raise ValueError("Unknown learning statistics input")
                fingerprint = values.get("fingerprint")
                if fingerprint is not None and (type(fingerprint) is not str or not fingerprint.strip()):
                    raise ValueError("Piece fingerprint must be a nonempty string")
                return self._reply(OK, engine.learning_statistics(fingerprint))
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
            if operation == "score.native_layout":
                return self._reply(OK, engine.geometry())
            if operation == "score.next_stage":
                if values:
                    raise ValueError("score.next_stage takes no input")
                # Heavy JSON was already encoded by the background prefetch
                # worker. The musical clock only transfers these bytes.
                return OK, engine.next_stage_score()
            if operation == "score.stage_ready":
                return self._reply(OK, engine.acknowledge_preloaded_stage(
                    stage_key=values["stage_key"], revision=values["revision"],
                    presentation_lead_beats=float(
                        values.get("presentation_lead_beats",0.0)),
                    presentation_clear_beats=(
                        float(values["presentation_clear_beats"])
                        if values.get("presentation_clear_beats") is not None else None),
                    continuation_clear_beats=values.get("continuation_clear_beats"),
                    continuation_header_beats=values.get("continuation_header_beats")))
            if operation == "score.stage_failed":
                return self._reply(OK, engine.report_preload_failure(
                    fingerprint=values["fingerprint"],
                    step_number=values["step_number"],
                    revision=values["revision"], error=values["error"]))
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
            elif operation == "library.health.start":
                return self._reply(OK, engine.start_library_health())
            elif operation == "settings.update":
                engine.set_preferences(**values)
            elif operation == "midi.device.select":
                engine.connect(values.get("name", ""))
            elif operation == "hardware.action":
                return self._reply(OK, engine.hardware_diagnostics_action(
                    values.get("action", "")))
            elif operation == "practice.command":
                engine.control(**values)
            else:
                return self._reply(UNKNOWN, {"error": f"Unknown operation: {operation}"})
            return self._reply(
                OK, engine.preferences() if operation == "settings.update" else engine.state())
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
