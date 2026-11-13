"""A stage handoff's renderer reuses the rasterized Verovio font (F1 round 4).

Re-rasterizing every SVG symbol for each new stage cost ~130 ms on the main
thread inside the next take's count-in (Hanon, Entertainer handoffs).
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from piano_teacher.server import import_piece
from piano_teacher.application.score_artifacts import ScoreArtifacts, ScoreSelection
from piano_teacher.preprocessing_cache import PreprocessingCache

ROOT = Path(__file__).resolve().parents[1]


def test_second_renderer_reuses_rasterized_font(tmp_path):
    godot = shutil.which("godot") or shutil.which("godot4")
    if not godot:
        pytest.skip("Godot 4 unavailable")
    # Keep the original pitch-probe source at its supported internal compiler
    # boundary; the desktop library correctly accepts MIDI only.
    source = ROOT / "tests/fixtures/native_pixel_pitch_probe.musicxml"
    piece, _ = import_piece(source)
    artifacts = ScoreArtifacts(PreprocessingCache(tmp_path / "cache"))
    selected = ScoreSelection(piece,piece.phrases[0],"both","glyph-cache-source",1,source.name)
    layout = artifacts.geometry(selected)
    assert layout["native_glyphs"] and layout["native_note_templates"]
    payload = tmp_path / "layout.json"
    payload.write_text(json.dumps(layout))
    run = subprocess.run(
        [godot, "--headless", "--audio-driver", "Dummy", "--path", str(ROOT / "godot"),
         "--script", str(ROOT / "tests/godot/glyph_raster_cache.gd"), "--", str(payload)],
        capture_output=True, text=True, timeout=120,
        env={**os.environ,"HOME":str(tmp_path/"home"),
             "XDG_DATA_HOME":str(tmp_path/"data"),"XDG_CONFIG_HOME":str(tmp_path/"config"),
             "XDG_CACHE_HOME":str(tmp_path/"godot-cache")})
    output = run.stdout + run.stderr
    (tmp_path / "godot.log").write_text(output)
    assert run.returncode == 0, output[-3000:]
    assert "GLYPH_CACHE_FAILURES:0" in output, output[-3000:]
    assert "SCRIPT ERROR" not in output, output[-3000:]
