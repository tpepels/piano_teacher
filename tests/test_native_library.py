"""Real curriculum assets must be accepted by the native Godot compositor."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_ala_measure_nine_curriculum_renders_natively(tmp_path):
    if not (shutil.which("godot") or shutil.which("godot4")):
        pytest.skip("Godot 4 unavailable")
    env = {**os.environ, "PIANO_TEACHER_NATIVE_NOTATION": "1"}
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_native_notation.py"),
         "--only", "Ala", "--measure", "9", "--output", str(tmp_path)],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["failed"] == 0
    stages = {(r["hand"], r["level"]) for r in report["results"]}
    assert stages == {("right", "original"), ("left", "skeleton"),
                      ("left", "original"), ("both", "original")}
    for case in report["results"]:
        assert case["native_ready"] and case["drawn_noteheads"] > 0
        assert case["drawn_noteheads"] == case["expected_noteheads"]
        assert not case["missing_noteheads"]
        assert case["linear_timeline"]


def test_real_application_uses_native_compositor_and_clock(tmp_path):
    if not (shutil.which("godot") or shutil.which("godot4")):
        pytest.skip("Godot 4 unavailable")
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts/smoke_native_notation.py"),
         "--output", str(tmp_path), "--measure", "10"],
        cwd=ROOT, env={**os.environ, "PIANO_TEACHER_NATIVE_NOTATION": "1"},
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = json.loads((tmp_path / "native-application.json").read_text())
    assert report["native_ready"] and report["visible"]
    assert report["drawn_noteheads"] > 0
    assert report["clock_samples"] >= 3 and report["linear_timeline"]
    assert report["first_bar"] == 9 and report["play_from_beat"] == 3


def test_peace_piece_cross_bar_attack_keeps_exact_timing_without_fallback(tmp_path):
    if not (shutil.which("godot") or shutil.which("godot4")):
        pytest.skip("Godot 4 unavailable")
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_native_notation.py"),
         "--only", "Peace_Piece", "--measure", "57", "--output", str(tmp_path)],
        cwd=ROOT, env={**os.environ, "PIANO_TEACHER_NATIVE_NOTATION": "1"},
        capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["failed"] == 0
    original = next(r for r in report["results"]
                    if r["hand"] == "both" and r["level"] == "original")
    # The real attack is .00625 beat before the next bar's tied continuation.
    # Bounded engraving must preserve that timing at a practical global scale.
    assert 0 < original["pixels_per_beat"] <= 480
    assert original["native_ready"] and original["linear_timeline"]
