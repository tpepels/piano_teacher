"""Actual rest-led tuplets need unobscured hooks, not a playhead-edge fit.

The retained original frames remain immutable. A fresh production Godot view
adds one unobscured witness; mutations alter its pixels, never expectations.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest

from piano_teacher.application.score_preparation import assemble_layout
from piano_teacher.notation.connector_pixels import verify_tuplet_pixels
from piano_teacher.notation.symbol_pixel_proof import bright


ROOT = Path(__file__).resolve().parents[1]
RETAINED = ROOT / "tests/fixtures/connector_pixels/moonlight-rest-voices"


def graphical(folder):
    report = verify_tuplet_pixels((folder / "score.musicxml").read_text(), folder, hand="right")
    rows = [row for row in report["measured"] if row["graphical"]]
    assert len(rows) == 1, report
    return rows[0]


def test_retained_playhead_over_hook_is_unavailable_rather_than_detached():
    row = graphical(RETAINED)
    assert row["status"] == "unverified", row
    failures = row["evidence"]["unavailable_witnesses"]
    assert len(failures) == 3
    assert all("playhead occludes" in failure["reason"] for failure in failures)


@pytest.fixture(scope="module")
def fresh_capture(tmp_path_factory):
    binary = shutil.which("godot") or shutil.which("godot4")
    if not binary or not os.environ.get("DISPLAY"):
        pytest.skip("Actual tuplet framebuffer regression requires Godot 4 and DISPLAY")
    folder = tmp_path_factory.mktemp("moonlight-tuplet")
    for name in ("score.musicxml", "verovio-0.svg"):
        shutil.copyfile(RETAINED / name, folder / name)
    model = json.loads((RETAINED / "model.json").read_text())
    source = SimpleNamespace(layout={}, pages=[(folder / "verovio-0.svg").read_text()])
    assets = assemble_layout(source, native_model=model,
                             notation_xml=(folder / "score.musicxml").read_text())
    fixture = folder / "fixture.json"
    fixture.write_text(json.dumps(dict(model=model, assets=assets)))
    result = subprocess.run([
        binary, "--path", str(ROOT / "godot"), "--rendering-method", "gl_compatibility",
        "--disable-vsync", "--max-fps", "0", "--resolution", "16x16",
        "--position", "-16384,-16384", "--script",
        str(ROOT / "tests/godot/native_moonlight_tuplet.gd"), "--", str(fixture), str(folder),
    ], env={**os.environ, "LIBGL_ALWAYS_SOFTWARE": "1"},
        capture_output=True, text=True, timeout=40)
    output = result.stdout + result.stderr
    (folder / "godot.log").write_text(output)
    assert result.returncode == 0, output
    assert "MOONLIGHT_TUPLET_CAPTURES:4" in output, output
    assert "SCRIPT ERROR" not in output and "Parse Error" not in output, output
    return folder


def test_real_godot_rest_led_tuplet_has_complete_unobscured_bracket(fresh_capture):
    row = graphical(fresh_capture)
    assert row["status"] == "verified", row
    assert row["source_ids"] == ["xml-p0-m0-e1", "xml-p0-m0-e2", "xml-p0-m0-e3"]
    assert [w["frame"] for w in row["evidence"]["witnesses"]] == ["native-1.00000.png"]
    assert len(row["evidence"]["unavailable_witnesses"]) == 3


@pytest.mark.parametrize("damage", ["erase", "move", "left-hook", "right-hook", "interrupt"])
def test_corrupted_fresh_godot_bracket_cannot_use_occluded_frames(fresh_capture, tmp_path, damage):
    baseline = graphical(fresh_capture)
    assert baseline["status"] == "verified", baseline
    witness = baseline["evidence"]["witnesses"][0]
    folder = tmp_path / damage
    shutil.copytree(fresh_capture, folder)
    path = folder / witness["frame"]
    with Image.open(path) as raw:
        image = raw.convert("RGB")
    pixels = np.asarray(image).copy()
    ink = bright(image)
    left, top, right, bottom = witness["bracket_bbox"]
    selected = np.zeros(ink.shape, dtype=bool)
    selected[top:bottom, left:right] = ink[top:bottom, left:right]
    nl, nt, nr, nb = witness["number_bbox"]
    selected[nt:nb, nl:nr] = False  # Keep the independent numeral intact.
    if damage in {"left-hook", "right-hook"}:
        edge = np.zeros_like(selected)
        start, stop = (left, left+5) if damage == "left-hook" else (right-5, right)
        edge[top+4:bottom+1, start:stop] = True
        selected &= edge
    elif damage == "interrupt":
        edge = np.zeros_like(selected)
        edge[:, left+10:left+15] = True
        selected &= edge
    assert selected.sum() >= 8, "Mutation must remove real bracket ink"
    ys, xs = np.nonzero(selected)
    old_ink = pixels[ys, xs].copy()
    pixels[ys, xs] = pixels[0, -1]
    if damage == "move":
        pixels[ys+round(2*witness["staff_gap"]), xs] = old_ink
    Image.fromarray(pixels).save(path)
    changed = graphical(folder)
    assert changed["status"] == "mismatch", changed
    assert "bracket" in changed["reason"].lower(), changed
