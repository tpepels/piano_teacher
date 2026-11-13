"""Real state snapshots conform to the versioned UI contract in every phase."""
from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

from piano_teacher import state_contract
from piano_teacher.server import PracticeEngine

ROOT = Path(__file__).resolve().parents[1]


def _snapshots(tmp_path):
    now = [1000.0]
    engine = PracticeEngine(tmp_path, enable_midi=False, clock=lambda: now[0])
    try:
        yield "empty", engine
        engine.load(str(ROOT / "midi" / "Moonlight_Sonata_I.midi"))
        yield "loaded", engine
        engine.midi.port = SimpleNamespace(closed=False)
        engine.start()
        yield "count_in", engine
        now[0] = engine.visual_transport.run_at + 1
        yield "playing", engine
        engine.control(action="pause")
        yield "paused", engine
        engine.control(action="resume")
        for _ in range(90):
            now[0] += 1
            engine.advance_clock()
        yield "after_take", engine
        engine.control(action="learn")
        yield "learn", engine
        engine.control(action="listen")
        yield "listen", engine
    finally:
        engine.db.close()


def test_every_phase_conforms_to_the_contract(tmp_path):
    phases = []
    for phase, engine in _snapshots(tmp_path):
        full = json.loads(json.dumps(engine.state()))
        polled = json.loads(json.dumps(engine.poll_state()))
        assert state_contract.problems(full) == [], (phase, state_contract.problems(full))
        assert state_contract.problems(polled) == [], phase
        assert full["schema_version"] == polled["schema_version"] == state_contract.VERSION
        for key in state_contract.STATIC_KEYS:
            assert key not in polled, (phase, key)
        phases.append(full.get("phase"))
    assert len(phases) == 8


def test_static_values_leave_the_per_frame_poll(tmp_path):
    engine = PracticeEngine(tmp_path, enable_midi=False)
    try:
        engine.load(str(ROOT / "midi" / "Moonlight_Sonata_I.midi"))
        full, polled = engine.state(), engine.poll_state()
        assert full["import_warnings"], "fixture imports with repairs"
        assert len(json.dumps(polled)) < len(json.dumps(full)) / 1.5
    finally:
        engine.db.close()


def test_the_problems_check_rejects_drift():
    assert state_contract.problems({"bpm": 60, "phase": "ready"}) == []
    assert state_contract.problems({"bpm": "60"}) == ["'bpm' is string, expected number"]
    assert state_contract.problems({"renamed_key": 1}) == ["unknown key 'renamed_key'"]


def test_godot_contract_is_generated_from_python():
    result = subprocess.run([sys.executable, str(ROOT / "scripts/generate_state_contract.py"),
                             "--check"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_godot_snapshot_consumers_read_only_contract_keys():
    """The main snapshot consumers cannot read a key the engine never sends."""
    consumers = [("godot/main.gd", "last_state"), ("godot/main.gd", "parsed"),
                 ("godot/practice_screen.gd", "parsed"),
                 ("godot/practice_state_presenter.gd", "parsed")]
    for path, name in consumers:
        source = (ROOT / path).read_text()
        if path == "godot/main.gd" and name == "parsed":
            # _on_state consumes the snapshot; other callbacks handle
            # separate learning.status responses with their own fields.
            source = source.split("func _on_state(", 1)[1].split("\nfunc ", 1)[0]
        keys = set(re.findall(name + r'\.get\("([a-z_0-9]+)"', source))
        assert keys <= set(state_contract.SCHEMA), (path, sorted(keys - set(state_contract.SCHEMA)))


@pytest.mark.skipif(shutil.which("godot") is None, reason="Godot unavailable")
def test_godot_validator_matches_python(tmp_path):
    script = tmp_path / "contract.gd"
    script.write_text('''extends SceneTree
const Contract := preload("res://state_contract.gd")
func _initialize() -> void:
    var ok: Array = Contract.problems({"schema_version":Contract.VERSION,"bpm":60.0,"phase":"ready"})
    var bad: Array = Contract.problems({"schema_version":Contract.VERSION,"bpm":"60","renamed":1})
    var stale: Array = Contract.problems({"schema_version":Contract.VERSION-1})
    print("CONTRACT ok=%d bad=%d stale=%d" % [ok.size(),bad.size(),stale.size()])
    quit()
''')
    result = subprocess.run(["godot", "--headless", "--path", str(ROOT / "godot"),
                             "--script", str(script)], capture_output=True, text=True, timeout=30)
    output = result.stdout + result.stderr
    assert "SCRIPT ERROR" not in output and "CONTRACT ok=0 bad=2 stale=1" in output, output
