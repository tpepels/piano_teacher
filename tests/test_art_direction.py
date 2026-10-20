"""Bounded composition checks on the real application, without an HTTP server.

For real MIDI/native rendering and full-resolution PNGs use
scripts/review_art_direction.py --render. This fixture only supplies state;
it never substitutes controls, notation assets, or layout code.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from scripts.review_art_direction import godot_command, validate_report

ROOT = Path(__file__).resolve().parents[1]
GODOT = shutil.which("godot") or shutil.which("godot4")


@pytest.mark.skipif(GODOT is None, reason="Godot 4 is not installed")
@pytest.mark.parametrize("size", [(1920, 1080), (800, 600)], ids=["desktop", "compact"])
def test_actual_application_composition_without_http(tmp_path: Path, size: tuple[int, int]):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "mode": "geometry", "output": str(tmp_path), "size": list(size),
        "render": False, "timeout_seconds": 25,
    }), encoding="utf-8")
    env = {**os.environ, "PIANO_TEACHER_NATIVE_NOTATION": "1",
           "XDG_DATA_HOME": str(tmp_path / "data"),
           "XDG_CONFIG_HOME": str(tmp_path / "config"),
           "XDG_CACHE_HOME": str(tmp_path / "cache")}
    command = godot_command(GODOT, config_path, size, render=False)
    try:
        result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True,
                                text=True, timeout=35)
    except subprocess.TimeoutExpired as exc:
        pytest.fail(f"Composition fixture exceeded its 35s bound: {exc}")
    transcript = result.stdout + result.stderr
    (tmp_path / "godot.log").write_text(transcript, encoding="utf-8")
    report_path = tmp_path / "art-direction.json"
    evidence = report_path.read_text(encoding="utf-8") if report_path.exists() else "No report"
    assert result.returncode == 0, transcript + "\n" + evidence
    assert not any(token in transcript for token in (
        "SCRIPT ERROR", "Parse Error", "ERROR:", "ART_DIRECTION_UNEXPECTED_HTTP",
    )), transcript
    report = json.loads(evidence)
    validate_report(report, size, output=tmp_path, require_native=False, render=False)
    assert report["mode"] == "geometry"
    assert report["display_server"] == "headless"
    assert report["network_requests"] == 0
    assert all(not sample["native"]["checked"] for sample in report["captures"])
    assert all(not sample["window_geometry"]["native_mode_checked"] for sample in report["captures"])
    settings = next(sample for sample in report["captures"] if sample["name"] == "settings")
    assert {key: row["caption"]["text"] for key, row in settings["settings_rows"].items()} == {
        "target_tempo": "Target tempo", "piano_volume": "Piano volume",
    }
    assert "ART_DIRECTION_FAILURES:0" in transcript
