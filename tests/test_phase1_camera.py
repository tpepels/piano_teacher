"""Camera acceptance through the production native app, offline and headless."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from piano_teacher.server import PracticeEngine

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def native_camera_run(tmp_path_factory):
    """Share the production app probe with migrated raster/smoke acceptance."""
    binary = shutil.which("godot") or shutil.which("godot4")
    if not binary:
        pytest.skip("Godot 4 unavailable")
    folder = tmp_path_factory.mktemp("native-camera")
    engine = PracticeEngine(folder / "cache", enable_midi=False)
    try:
        engine.load(str(ROOT / "tests/fixtures/native_pixel_pitch_probe.musicxml"))
        payload = {"layout": engine.geometry(native_notes=True),
                   "model": engine.semantic_score()}
    finally:
        engine.db.close()
    fixture = folder / "native.json"
    fixture.write_text(json.dumps(payload))
    env = dict(os.environ)
    for name in ("PIANO_TEACHER_RENDERER", "PIANO_TEACHER_NATIVE_NOTATION",
                 "PIANO_TEACHER_TIMELINE_PREVIEW", "PIANO_TEACHER_PIXELS_PER_BEAT",
                 "PIANO_TEACHER_NATIVE_SCORE", "PIANO_TEACHER_EXACT_VEROVIO_GRID"):
        env.pop(name, None)
    env.update(XDG_DATA_HOME=str(folder / "data"),
               XDG_CONFIG_HOME=str(folder / "config"))
    proc = subprocess.run(
        [binary, "--headless", "--path", str(ROOT / "godot"), "--script",
         str(ROOT / "tests/godot/native_camera.gd"), "--", str(fixture),
         "--phase0-smoke"],
        env=env, capture_output=True, text=True, timeout=45)
    output = proc.stdout + proc.stderr
    assert proc.returncode == 0, output
    assert "SCRIPT ERROR" not in output and "Parse Error" not in output, output
    marker = "NATIVE_CAMERA_REPORT:"
    report = next((line.removeprefix(marker) for line in output.splitlines()
                   if line.startswith(marker)), None)
    assert report is not None, output
    return json.loads(report), output


def test_native_projection_uses_source_beats_under_fixed_playhead(native_camera_run):
    report, _ = native_camera_run
    assert {s["label"] for s in report["samples"]} >= {
        "ready", "lead", "playing", "paused", "seek", "stopped", "restart"}
    for sample in report["samples"]:
        assert sample["heads"], sample
        for head in sample["heads"]:
            expected = (.42 * sample["width"] +
                        (head["onset"] - sample["musical_beat"]) * sample["density"])
            assert head["x"] == pytest.approx(expected, abs=.002), sample


def test_native_camera_keeps_ink_visible_after_resize_and_seek(native_camera_run):
    report, _ = native_camera_run
    assert len({s["width"] for s in report["samples"]}) >= 2
    assert any(s["play_from"] > 0 for s in report["samples"])
    for sample in report["samples"]:
        visible = [head for head in sample["heads"]
                   if 0 <= head["x"] <= sample["width"]
                   and 0 <= head["y"] <= sample["height"]]
        assert visible, sample
        assert sample["visible_count"] == len(visible), sample
        assert sample["staff_gap"] >= 14, sample
    assert report["clipped"]


def test_transport_and_resize_reuse_native_model_and_atlas(native_camera_run):
    report, _ = native_camera_run
    assert report["same_timeline"] and report["same_index"] and report["same_atlas"]
    assert len({s["density"] for s in report["samples"]}) == 1


def test_visible_event_lookup_excludes_distant_source_notes(native_camera_run):
    report, _ = native_camera_run
    assert report["indexed_beats"]
    assert all(0 <= beat <= 1.25 for beat in report["indexed_beats"])
    assert report["scanned_events"] == len(report["indexed_beats"])
    assert report["scanned_events"] < report["total_events"]


def test_pause_freezes_native_ink_and_resume_uses_real_clock(native_camera_run):
    report, _ = native_camera_run
    assert report["pause_frozen"]
    assert report["resume_advanced"]
    assert report["clock_matched"]


def test_frame_budget_is_retained():
    assert "Engine.max_fps = 60" in (ROOT / "godot/main.gd").read_text()
