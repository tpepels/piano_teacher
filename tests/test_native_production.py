"""Production must use native notation even with retired renderer switches."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from piano_teacher.server import PracticeEngine

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("renderer", ["default", "retired-switches"])
def test_native_production_readiness_and_failure_gate(tmp_path, renderer):
    binary = shutil.which("godot") or shutil.which("godot4")
    if not binary:
        pytest.skip("Godot 4 unavailable")
    engine = PracticeEngine(tmp_path / "cache", enable_midi=False)
    try:
        engine.load(str(ROOT / "tests/fixtures/native_pixel_pitch_probe.musicxml"))
        payload = {"layout": engine.geometry(native_notes=True),
                   "model": engine.semantic_score()}
    finally:
        engine.db.close()
    fixture = tmp_path / "native.json"
    fixture.write_text(json.dumps(payload))
    env = dict(os.environ)
    for name in ("PIANO_TEACHER_RENDERER", "PIANO_TEACHER_NATIVE_NOTATION",
                 "PIANO_TEACHER_TIMELINE_PREVIEW", "PIANO_TEACHER_NATIVE_SCORE",
                 "PIANO_TEACHER_EXACT_VEROVIO_GRID"):
        env.pop(name, None)
    args = [str(fixture)]
    if renderer == "retired-switches":
        env.update(PIANO_TEACHER_RENDERER="legacy", PIANO_TEACHER_NATIVE_NOTATION="0",
                   PIANO_TEACHER_TIMELINE_PREVIEW="1", PIANO_TEACHER_NATIVE_SCORE="1",
                   PIANO_TEACHER_EXACT_VEROVIO_GRID="1")
        args += ["--legacy-notation", "--timeline-preview"]
    proc = subprocess.run(
        [binary, "--headless", "--path", str(ROOT / "godot"), "--script",
         str(ROOT / "tests/godot/native_production.gd"), "--", *args],
        env=env, capture_output=True, text=True, timeout=45)
    output = proc.stdout + proc.stderr
    assert proc.returncode == 0, output
    assert "NATIVE_PRODUCTION_FAILURES:0" in output, output
    assert "SCRIPT ERROR" not in output and "Parse Error" not in output, output
