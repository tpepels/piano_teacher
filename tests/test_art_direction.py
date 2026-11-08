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

from scripts.review_art_direction import embedded_python_env, godot_command, validate_report

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
    env = {**os.environ,
           "XDG_DATA_HOME": str(tmp_path / "data"),
           "XDG_CONFIG_HOME": str(tmp_path / "config"),
           "XDG_CACHE_HOME": str(tmp_path / "cache"),
           **embedded_python_env()}
    env.pop("PIANO_TEACHER_NATIVE_NOTATION", None)
    env.pop("PIANO_TEACHER_RENDERER", None)
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


@pytest.mark.skipif(GODOT is None, reason="Godot 4 is not installed")
def test_art_direction_cli_geometry_needs_no_renderer_opt_in(tmp_path, monkeypatch):
    from scripts.review_art_direction import main

    monkeypatch.delenv("PIANO_TEACHER_NATIVE_NOTATION", raising=False)
    monkeypatch.delenv("PIANO_TEACHER_RENDERER", raising=False)
    assert main(["--geometry-only", "--sizes", "800x600",
                 "--output", str(tmp_path)]) == 0
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["status"] == "passed"


def native_composition_report():
    """Minimal complete desktop evidence using the current Godot report schema."""
    geometry = {"physical_viewport": {"x": 0, "y": 0, "width": 800, "height": 600},
                "physical_scale": [1, 1], "content_scale": 1, "native_mode_checked": False}
    rect = {"x": 0, "y": 0, "width": 100, "height": 100}
    captures = []
    for name in ("practice_ready", "practice_playing", "practice_paused",
                 "library", "lesson_path", "settings"):
        practice = name.startswith("practice_")
        sample = {"name": name, "screen": "practice" if practice else
                  ("lesson" if name == "lesson_path" else name),
                  "phase": name.removeprefix("practice_") if practice else "paused",
                  "controls": [{"name": "transport"}], "window_geometry": geometry,
                  "captions": [{"text": "Play", "content_width": 80, "longest_word_width": 40}],
                  "rects": {key: rect for key in ("application", "score_stage", "score_frame",
                            "transport", "primary_transport", "navigation")},
                  "native": {"checked": True, "renderer_script": "res://notation/native/view.gd",
                             "score_ready": True, "native_ready": True, "visible": True,
                             "drawn_noteheads": 3, "visible_noteheads": 2,
                             "revision": 4, "state_revision": 4, "layout_revision": 4,
                             "rendered_revision": 4, "model_revision": 4,
                             "failure_reason": "", "action_pending": False, "pending_action": ""},
                  "screenshot": None}
        if name == "settings":
            sample["settings_rows"] = {key: {
                "caption": {"line_count": 1, "content_width": 80, "text_width": 40,
                            "rect": {"height": 20}},
                "height_limit": 30, "row": {"height": 20}, "control": {"height": 20}}
                for key in ("target_tempo", "piano_volume")}
        captures.append(sample)
    return {"schema_version": 1, "viewport": [800, 600], "render": False,
            "display_server": "headless", "window_geometry": geometry,
            "failures": [], "captures": captures}


def test_art_direction_accepts_native_readiness_without_removed_flags(tmp_path):
    validate_report(native_composition_report(), (800, 600), output=tmp_path,
                    require_native=True, render=False)


@pytest.mark.parametrize("field,value,detail", [
    ("renderer_script", "res://notation/diagnostics/timeline_preview.gd", "renderer"),
    ("score_ready", False, "ready"),
    ("native_ready", False, "ready"),
    ("visible_noteheads", 0, "noteheads"),
    ("model_revision", 3, "stale"),
])
def test_art_direction_rejects_invalid_native_evidence(tmp_path, field, value, detail):
    report = native_composition_report()
    # Stale opt-in claims must not substitute for actual renderer/readiness evidence.
    report["native_environment"] = "1"
    for capture in report["captures"]:
        capture["native"]["enabled"] = True
    report["captures"][0]["native"][field] = value
    with pytest.raises(RuntimeError, match=detail):
        validate_report(report, (800, 600), output=tmp_path, require_native=True, render=False)
