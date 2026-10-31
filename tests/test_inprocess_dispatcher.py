"""The in-process dispatcher has the same *semantic* routes as desktop HTTP.

These contracts are independent of GDExtension, allowing cheap tests of the
Python engine and avoiding a second behavioral implementation in C++.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from piano_teacher.inprocess import EngineCommands, InMemoryVisualPublisher
from piano_teacher.server import PracticeEngine


class FakeEngine:
    def __init__(self):
        self.controls = []
        self.changes = []
        self.loaded = None
        self.library_id = None

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

    def set_preferences(self, **kwargs):
        self.changes.append(kwargs)

    def load(self, path):
        self.loaded = path

    def load_library(self, identifier):
        self.library_id = identifier


def _decode(result):
    status, body = result
    return status, json.loads(body)


def test_native_dispatcher_get_routes_match_expected_ui_contract():
    bridge = EngineCommands(engine=FakeEngine())
    assert _decode(bridge.request("GET", "/state")) == (
        200, {"phase": "ready", "revision": 17, "source": None})
    assert _decode(bridge.request("GET", "/devices")) == (
        200, {"devices": ["Bluetooth Keyboard"]})
    assert _decode(bridge.request("GET", "/library")) == (200, {"pieces": ["first.mid"]})
    assert _decode(bridge.request("GET", "/lesson")) == (200, {"steps": [1, 2]})
    assert _decode(bridge.request("GET", "/score/layout?native=0")) == (200, {"native": False})
    assert _decode(bridge.request("GET", "/score/layout?native=1")) == (200, {"native": True})
    assert _decode(bridge.request("GET", "/score/model")) == (200, {"revision": 17})
    assert bridge.request("GET", "/demo.wav?token=abc") == (200, b"RIFFabc")


def test_native_dispatcher_post_and_errors():
    engine = FakeEngine()
    bridge = EngineCommands(engine=engine)
    assert _decode(bridge.request("POST", "/control", '{"action":"play"}'))[0] == 200
    assert engine.controls == [{"action": "play"}]
    assert _decode(bridge.request("POST", "/settings", '{"metronome":false}'))[0] == 200
    assert engine.changes == [{"metronome": False}]
    assert _decode(bridge.request("POST", "/library/open", '{"id":"first.mid"}'))[0] == 200
    assert engine.library_id == "first.mid"
    assert _decode(bridge.request("POST", "/load", '{"path":"/music/first.mid"}'))[0] == 200
    assert engine.loaded == "/music/first.mid"
    assert _decode(bridge.request("GET", "/missing"))[0] == 404
    assert _decode(bridge.request("PUT", "/state"))[0] == 405
    assert _decode(bridge.request("POST", "/control", "[]"))[0] == 400
    assert _decode(bridge.request("POST", "/load", "{}"))[0] == 400


def test_real_embedded_engine_does_not_create_network_visual_publisher(tmp_path):
    visual = InMemoryVisualPublisher()
    engine = PracticeEngine(tmp_path, enable_midi=False, visual_publisher=visual)
    bridge = EngineCommands(engine=engine)
    try:
        status, values = _decode(bridge.request("GET", "/state"))
        assert status == 200 and not values["loaded"]
        assert not hasattr(engine.midi_visual_publisher, "socket")
        status, values = _decode(bridge.request("GET", "/settings"))
        assert status == 200 and "exercise_strategy" in values
        visual.publish({"sequence": 4, "transport_id": 11,
                        "status": "on_time", "pitch": 60})
        assert bridge.drain_midi_events(3)[0]["sequence"] == 4
        assert bridge.drain_midi_events(4) == []
    finally:
        engine.db.close()
