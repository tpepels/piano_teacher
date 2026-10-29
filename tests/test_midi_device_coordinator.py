"""Godot device scanning, picker and reconnect policies are application-independent."""
from pathlib import Path
import shutil
import subprocess
import pytest


def test_midi_device_coordinator_godot():
    godot = shutil.which("godot") or shutil.which("godot4")
    if godot is None:
        pytest.skip("Godot 4 unavailable")
    root = Path(__file__).resolve().parents[1]
    run = subprocess.run([
        godot, "--headless", "--path", str(root/"godot"),
        "--audio-driver", "Dummy", "--script",
        str(root/"tests/godot/midi_device_coordinator.gd")],
        capture_output=True, text=True, timeout=25)
    output = run.stdout+run.stderr
    assert run.returncode == 0, output
    assert not any(x in output for x in ("SCRIPT ERROR","ERROR:","Parse Error")), output
    assert "MIDI_DEVICE_COORDINATOR_FAILURES:0" in output, output
