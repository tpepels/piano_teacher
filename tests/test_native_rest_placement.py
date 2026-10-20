"""Pixel and polyphonic-rest regressions against genuine Verovio glyphs."""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_verovio_native_rest_positions_and_pixels(tmp_path):
    godot = shutil.which("godot") or shutil.which("godot4")
    xvfb = shutil.which("xvfb-run")
    if not godot or not xvfb:
        pytest.skip("Godot 4 with Xvfb required for real native pixel capture")
    from piano_teacher.notation.assets.glyphs import native_glyphs
    from piano_teacher.notation.assets.notes import note_templates
    from piano_teacher.notation.assets.ties import tie_templates

    fixture = tmp_path / "rest-atlas.json"
    fixture.write_text(json.dumps({
        "glyphs": native_glyphs(),
        "notes": note_templates(),
        "ties": tie_templates(),
    }))
    output = Path(os.environ.get(
        "PIANO_TEACHER_REST_SCREENSHOTS",
        str(tmp_path / "screenshots")))
    cmd = [xvfb, "-a", "-s", "-screen 0 1700x1000x24",
           godot, "--path", str(ROOT / "godot"),
           "--rendering-method", "gl_compatibility",
           "--script", str(ROOT / "tests/godot/native_rest_pixels.gd"),
           "--", str(fixture), str(output)]
    result = subprocess.run(cmd, env={
        **os.environ, "LIBGL_ALWAYS_SOFTWARE": "1",
        "PIANO_TEACHER_NATIVE_NOTATION": "1",
    }, capture_output=True, text=True, timeout=100)
    transcript = result.stdout + result.stderr
    assert result.returncode == 0, transcript
    assert "NATIVE_REST_PIXEL_FAILURES:0" in transcript, transcript
    assert "SCRIPT ERROR" not in transcript and "Parse Error" not in transcript
    assert (output / "native-rests-both-staves.png").stat().st_size > 0
    assert (output / "native-double-dotted-rests.png").stat().st_size > 0
    assert (output / "native-polyphonic-rests.png").stat().st_size > 0
