"""Status-ink GPU warmup must survive immediate parent teardown safely."""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
GODOT = shutil.which("godot") or shutil.which("godot4")

WARMUP_LIFETIME = r"""
extends SceneTree
const Warmup := preload("res://status_ink_warmup.gd")

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    # Regression: the old Main coroutine resumed after the application was
    # freed while it awaited three process_frame events.
    var early_parent := Node2D.new()
    root.add_child(early_parent)
    var early := Warmup.new()
    early_parent.add_child(early)
    early_parent.free()
    for _i in range(5):
        await process_frame
    var early_safe: bool = not is_instance_valid(early)

    # An undisturbed warmup must remain for the initial frame and free
    # itself after its bounded render-preparation lifetime.
    var parent := Node2D.new()
    root.add_child(parent)
    var normal := Warmup.new()
    parent.add_child(normal)
    await process_frame
    var initial_alive: bool = is_instance_valid(normal)
    for _i in range(5):
        await process_frame
    var expired: bool = not is_instance_valid(normal)
    parent.free()
    var failures := 0 if early_safe and initial_alive and expired else 1
    print("STATUS_INK_WARMUP_FAILURES:", failures)
    quit(failures)
"""


@pytest.mark.skipif(GODOT is None, reason="Godot 4 unavailable")
def test_status_ink_warmup_owner_teardown_and_bounded_expiry(tmp_path):
    script = tmp_path / "status_ink_warmup_lifetime.gd"
    script.write_text(WARMUP_LIFETIME)
    proc = subprocess.run(
        [GODOT, "--headless", "--path", str(ROOT / "godot"),
         "--audio-driver", "Dummy", "--script", str(script)],
        text=True, capture_output=True, timeout=20,
    )
    output = proc.stdout + proc.stderr
    assert proc.returncode == 0, output
    assert "SCRIPT ERROR" not in output and "ERROR:" not in output, output
    assert "STATUS_INK_WARMUP_FAILURES:0" in output, output
