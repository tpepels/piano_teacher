"""Independent multi-frame rail evidence on real dense source passages.

These are intentionally difficult original-source excerpts from the 24-shard
audit. Keep their noteheads as source-bound pixel obligations; remove neither
cases nor limits to improve the result. Corrupting ONE current photograph must
still fail even when other photographs contain intact rails.
"""
from collections import Counter
import json
import os
from pathlib import Path
import shutil
import subprocess

import numpy as np
import pytest
from PIL import Image, ImageDraw

from piano_teacher.notation.phase3_pixels import verify_all_notehead_pixels
from piano_teacher.notation.pixel_proof import detect_staff_lines
from piano_teacher.notation.proof import read_written_score
from scripts.check_native_verovio_overlay import AuditCase, fixture

ROOT = Path(__file__).resolve().parents[1]
CASES = (
    ("hanon", "Le_Pianiste_virtuose_-_Première_partie_(1-20)_-_C_L_Hanon.midi", 37, 40, "left"),
    ("chopin", "Chopin_-_Nocturne_Op_9_No_2_(E_Flat_Major).midi", 13, 16, "right"),
    ("debussy", "Clair_de_Lune_–_Debussy.midi", 33, 36, "right"),
)


@pytest.mark.parametrize("name,filename,first,last,hand", CASES)
def test_current_photographic_rails_and_negative_control(
    name, filename, first, last, hand, tmp_path,
):
    godot = shutil.which("godot") or shutil.which("godot4")
    assert godot, "Godot 4.7.2 actual framebuffer is required"
    prepared, _ = fixture(AuditCase(
        f"full-audit-{name}-rails", filename, first, last, hand))
    assert not prepared["source_errors"], prepared["source_errors"]
    xml = prepared["xml"]
    symbols = [
        event for event in read_written_score(xml).symbols
        if event["kind"] == "note" and event["visible"] and event["staff"] == hand
    ]
    beats = sorted({round(float(event["beat"]), 8) for event in symbols})
    assert len(beats) >= 3, (name, beats)
    selected = sorted({beats[0], beats[len(beats)//2], beats[-1]})
    expected = sum(sum(abs(float(event["beat"])-beat) < 1e-8
                       for event in symbols) for beat in selected)
    assert expected >= 3
    prepared.update(sample_beats=selected, phase3_full=True)
    folder = tmp_path / name
    folder.mkdir()
    (folder / "score.musicxml").write_text(xml)
    (folder / "fixture.json").write_text(json.dumps(prepared))
    run = subprocess.run([
        godot, "--path", str(ROOT / "godot"),
        "--audio-driver", "Dummy", "--rendering-method", "gl_compatibility",
        "--script", str(ROOT / "tests/godot/native_verovio_overlay.gd"),
        "--", str(folder / "fixture.json"), str(folder),
    ], capture_output=True, text=True, timeout=125,
       env={**os.environ, "LIBGL_ALWAYS_SOFTWARE": "1"})
    (folder / "godot.log").write_text(run.stdout + run.stderr)
    assert run.returncode == 0, (run.stdout + run.stderr)[-4000:]

    report = verify_all_notehead_pixels(xml, folder, hand=hand)
    (folder / "native-rail-proof.json").write_text(json.dumps(report, indent=2))
    selected_rows = [
        row for row in report["measured"]
        if any(abs(float(row["beat"])-beat) < 1e-8 for beat in selected)
    ]
    observed = Counter(row["status"] for row in selected_rows)
    assert len(selected_rows) == expected
    assert observed["verified"] == expected, {
        "source": filename, "selected": selected,
        "statuses": dict(observed),
        "unverified": [r for r in selected_rows if r["status"] != "verified"],
    }

    # A reference from OTHER good frames is not permission to manufacture
    # a missing current rail. Erase one actual gray line in just one frame.
    photos = []
    for beat in selected:
        with Image.open(folder / f"native-{beat:.5f}.png") as image:
            photos.append(np.asarray(image.convert("RGB"), dtype=np.uint8))
    rails = detect_staff_lines(Image.fromarray(np.minimum.reduce(photos)))
    missing_line = round(rails[hand].lines[2])
    path = folder / f"native-{selected[0]:.5f}.png"
    with Image.open(path) as image:
        broken = image.convert("RGB")
    ImageDraw.Draw(broken).rectangle(
        (0, missing_line-3, broken.width-1, missing_line+3),
        fill=broken.getpixel((0, 0)))
    broken.save(path)
    damaged = verify_all_notehead_pixels(xml, folder, hand=hand)
    damaged_rows = [
        row for row in damaged["measured"]
        if abs(float(row["beat"])-selected[0]) < 1e-8
    ]
    assert damaged_rows
    assert all(row["status"] != "verified" for row in damaged_rows), damaged_rows
