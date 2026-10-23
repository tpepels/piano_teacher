"""Exercise the native compositor with source fragments and a fixed beat grid."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_native_fragment_anchors_and_accidental_collisions(tmp_path):
    binary = shutil.which("godot") or shutil.which("godot4")
    if not binary:
        pytest.skip("Godot 4 unavailable")
    from piano_teacher.notation.assets.glyphs import native_glyphs
    fixture = tmp_path / "symbols.json"
    fixture.write_text(json.dumps(native_glyphs()))
    result = subprocess.run(
        [binary, "--headless", "--path", str(ROOT / "godot"),
         "--script", str(ROOT / "tests/godot/native_fragment_geometry.gd")],
        env={**os.environ, "PIANO_TEACHER_NATIVE_NOTATION": "1",
             "PIANO_TEACHER_SYMBOL_FIXTURE": str(fixture)},
        text=True, capture_output=True, timeout=60,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "NATIVE_FRAGMENT_FAILURES:0" in output, output
    assert "SCRIPT ERROR" not in output and "Parse Error" not in output, output


def test_native_slur_preserves_original_texture_pixels(tmp_path):
    binary = shutil.which("godot") or shutil.which("godot4")
    if not binary or not os.environ.get("DISPLAY"):
        pytest.skip("Godot with a display is required for pixel verification")
    import verovio
    from piano_teacher.score import _create_verovio_toolkit
    from piano_teacher.notation.assets.slurs import extract_slurs

    xml = """<score-partwise version="4.0"><work><work-title> </work-title></work>
      <movement-title> </movement-title><part-list>
      <score-part id="P"><part-name>Piano</part-name></score-part></part-list>
      <part id="P"><measure number="1"><attributes><divisions>4</divisions>
      <time><beats>4</beats><beat-type>4</beat-type></time>
      <clef><sign>G</sign><line>2</line></clef></attributes>
      <note id="s1"><pitch><step>C</step><octave>5</octave></pitch>
      <duration>4</duration><type>quarter</type>
      <notations><slur type="start" number="1"/></notations></note>
      <note id="s2"><pitch><step>G</step><octave>5</octave></pitch>
      <duration>4</duration><type>quarter</type>
      <notations><slur type="stop" number="1"/></notations></note>
      <note><rest/><duration>8</duration><type>half</type></note>
      </measure></part></score-partwise>"""
    toolkit = _create_verovio_toolkit(verovio)
    assert toolkit.setOptions({"inputFrom": "xml", "scale": 48,
        "pageWidth": 900, "pageHeight": 650, "svgViewBox": True,
        "svgBoundingBoxes": True, "svgContentBoundingBoxes": True})
    assert toolkit.loadData(xml)
    atlas = extract_slurs([toolkit.renderToSVG(1)], xml, {
        "notation_events": [{"id": i, "kind": "note"} for i in ("s1", "s2")]})
    assert set(atlas) == {"s1|s2"}
    fixture = tmp_path / "slur.json"
    fixture.write_text(json.dumps(atlas))
    result = subprocess.run(
        [binary, "--path", str(ROOT / "godot"), "--windowed",
         "--resolution", "640x240", "--rendering-method", "gl_compatibility",
         "--script", str(ROOT / "tests/godot/native_slur_pixels.gd")],
        env={**os.environ, "PIANO_TEACHER_NATIVE_NOTATION": "1",
             "PIANO_TEACHER_SLUR_FIXTURE": str(fixture)},
        text=True, capture_output=True, timeout=60,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "NATIVE_SLUR_PIXEL_FAILURES:0" in output, output
    assert "SCRIPT ERROR" not in output and "Parse Error" not in output, output
