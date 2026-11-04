"""The in-memory command dispatcher preserves Godot/engine contracts.

These contracts are independent of GDExtension, allowing cheap tests of the
Python engine and avoiding a second behavioral implementation in C++.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from piano_teacher.inprocess import EngineCommands
from piano_teacher.live_event_ring import LiveEventRing
from piano_teacher.server import PracticeEngine


class FakeEngine:
    def __init__(self):
        self.controls = []
        self.changes = []
        self.library_id = None

    def advance_clock(self):
        self.ticks = getattr(self, "ticks", 0) + 1
        return 20

    def state(self):
        return {"phase": "ready", "revision": 17, "source": self.library_id}

    def preferences(self):
        return {"metronome": True}

    def library_listing(self):
        return {"pieces": ["first.mid"]}

    def library_health_status(self):
        return {"running": False}

    def lesson_overview(self):
        return {"steps": [1, 2]}

    def ports(self):
        return ["Bluetooth Keyboard"]

    def semantic_score(self):
        return {"revision": 17}

    def geometry(self, native_notes=True):
        return {"native": native_notes}

    def demo_audio(self, token):
        return SimpleNamespace(read_bytes=lambda: b"RIFF" + token.encode())

    def control(self, **kwargs):
        self.controls.append(kwargs)

    def report_preload_failure(self, **kwargs):
        self.reported_native_failure = kwargs
        return {"accepted": True, "revision": kwargs["revision"]}

    def set_preferences(self, **kwargs):
        self.changes.append(kwargs)

    def load_library(self, identifier):
        self.library_id = identifier


def _decode(result):
    status, body = result
    return status, json.loads(body)


def test_typed_read_operations_follow_the_app_contract():
    bridge = EngineCommands(engine=FakeEngine())
    assert _decode(bridge.request("state.snapshot")) == (
        0, {"phase": "ready", "revision": 17, "source": None})
    assert _decode(bridge.request("midi.devices")) == (
        0, {"devices": ["Bluetooth Keyboard"]})
    assert _decode(bridge.request("library.catalog")) == (
        0, {"pieces": ["first.mid"]})
    assert _decode(bridge.request("lesson.overview")) == (
        0, {"steps": [1, 2]})
    assert _decode(bridge.request("score.native_layout")) == (0, {"native": True})
    assert _decode(bridge.request("score.semantic")) == (0, {"revision": 17})
    assert bridge.request("listen.audio", '{"token":"abc"}') == (0, b"RIFFabc")


def test_typed_mutations_and_invalid_operands():
    engine = FakeEngine()
    bridge = EngineCommands(engine=engine)
    assert _decode(bridge.request("practice.command", '{"action":"play"}'))[0] == 0
    assert engine.controls == [{"action": "play"}]
    assert _decode(bridge.request("settings.update", '{"metronome":false}'))[0] == 0
    assert engine.changes == [{"metronome": False}]
    assert _decode(bridge.request("library.open", '{"id":"first.mid"}'))[0] == 0
    assert engine.library_id == "first.mid"
    assert _decode(bridge.request("unknown.operation"))[0] == 2
    assert _decode(bridge.request("practice.command", "[]"))[0] == 1
    assert _decode(bridge.request("library.open", "{}"))[0] == 1
    assert _decode(bridge.request("state.snapshot", '{"mutate":true}'))[0] == 1


def test_real_embedded_engine_has_one_shared_transport_and_event_ring(tmp_path):
    visual = LiveEventRing()
    engine = PracticeEngine(tmp_path, enable_midi=False, live_events=visual)
    bridge = EngineCommands(engine=engine)
    try:
        status, values = _decode(bridge.request("state.snapshot"))
        assert status == 0 and not values["loaded"]
        assert not hasattr(engine.live_events, "socket")
        status, values = _decode(bridge.request("settings.snapshot"))
        assert status == 0 and "exercise_strategy" in values
        visual.publish({"sequence": 4, "transport_id": 11,
                        "status": "on_time", "pitch": 60})
        assert bridge.drain_midi_events(3)[0]["sequence"] == 4
        assert bridge.drain_midi_events(4) == []
        status, payload = _decode(bridge.request("midi.events", '{"since":3}'))
        assert status == 0 and payload[0]["sequence"] == 4
        assert _decode(bridge.request("midi.events", '{"since":4}')) == (0, [])
        assert _decode(bridge.request("midi.events", '{"since":-1}'))[0] == 1
    finally:
        engine.db.close()


def test_worker_tick_is_independent_of_snapshot_requests():
    engine = FakeEngine()
    bridge = EngineCommands(engine=engine)
    assert bridge.tick() == 20
    assert bridge.tick() == 20
    assert engine.ticks == 2
    assert _decode(bridge.request("state.snapshot"))[0] == 0
    assert engine.ticks == 2


def test_native_failure_command_is_typed_and_source_bound():
    fake = FakeEngine()
    bridge = EngineCommands(engine=fake)
    report = {"fingerprint": "piece", "step_number": 3, "revision": 12,
              "error": "unrenderable authentic beam"}
    status, body = _decode(bridge.request(
        "score.stage_failed", json.dumps(report)))
    assert status == 0 and body == {"accepted": True, "revision": 12}
    assert fake.reported_native_failure == report
    assert _decode(bridge.request("score.stage_failed", "{}"))[0] == 1
    assert _decode(bridge.request(
        "score.stage_failed", json.dumps({"error": "stale"})))[0] == 1
