"""C4/C5/C6 framebuffer gate: all six statuses on real filled and hollow heads.

Renders the production NativeView with real Verovio assets (tests/godot/
status_palette_framebuffer.gd), then measures the PNG: filled heads become the
exact tint, hollow heads are tinted softly inside their own mask (no ring), and
the five tints are pairwise distinct. Set STATUS_PALETTE_SAMPLE to a path to
keep the graded frame as a sample image.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import numpy as np
from PIL import Image
import pytest

ROOT = Path(__file__).resolve().parents[1]
ORDER = ["unplayed", "hit", "missed", "late", "early_release", "early_onset"]


@pytest.fixture(scope="module")
def sheet(tmp_path_factory):
    from scripts.check_native_verovio_overlay import AuditCase, fixture
    from test_native_fingering import _godot, _run_godot

    folder = tmp_path_factory.mktemp("status-palette")
    data, _ = fixture(AuditCase("status-palette",
                                "tests/fixtures/status_palette.musicxml", 1, 7, "both"))
    payload = folder / "fixture.json"
    payload.write_text(json.dumps(data))
    result = _run_godot([*_godot(), "--path", str(ROOT / "godot"),
        "--rendering-method", "gl_compatibility", "--audio-driver", "Dummy",
        "--script", str(ROOT / "tests/godot/status_palette_framebuffer.gd"),
        "--", str(payload), str(folder)], timeout=90)
    assert result.returncode == 0 and "SCRIPT ERROR" not in result.stdout + result.stderr
    report = json.loads((folder / "status-report.json").read_text())
    frames = {f["name"]: f for f in report["frames"]}
    images = {n: np.asarray(Image.open(folder / f["file"]).convert("RGB")).astype(int)
              for n, f in frames.items()}
    if os.environ.get("STATUS_PALETTE_SAMPLE"):
        shutil.copy(folder / frames["graded"]["file"], os.environ["STATUS_PALETTE_SAMPLE"])
    return report, frames, images


def _rgb(v):
    return np.array(v[:3], dtype=float) * 255


def _heads(report, frames):
    for item in frames["graded"]["instances"]:
        status = report["expected"].get(item["event_id"])
        if status is not None:
            yield item, status


def test_every_status_is_recorded_on_filled_and_hollow_heads(sheet):
    report, frames, _ = sheet
    seen = {(status, item["head"] == "head_black") for item, status in _heads(report, frames)}
    assert seen == {(s, f) for s in ORDER for f in (True, False)}
    for item, status in _heads(report, frames):
        assert item["status"] == status


def test_filled_heads_are_the_exact_tint_and_hollow_heads_are_softly_tinted(sheet):
    report, frames, images = sheet
    base, graded = images["baseline"], images["graded"]
    for item, status in _heads(report, frames):
        x, y = (int(round(v)) for v in item["position"])
        r = max(1, int(item["gap"] * .12))
        b = base[y - r:y + r + 1, x - r:x + r + 1].astype(float)
        g = graded[y - r:y + r + 1, x - r:x + r + 1].astype(float)
        if status == "unplayed":
            assert np.array_equal(b, g)
            continue
        tint = _rgb(report["tints"][status])
        if item["head"] == "head_black":
            assert np.abs(g - tint).max() <= 8, (status, g.mean((0, 1)))
        else:
            # C5: readable (>= 20% toward the status hue), soft (<= 75%).
            along = ((g - b) * (tint - b)).sum(axis=2) / np.maximum(
                ((tint - b) ** 2).sum(axis=2), 1.0)
            assert .2 <= along.mean() <= .75, (status, along.mean())


def test_the_five_status_hues_are_clearly_distinct(sheet):
    report, _, _ = sheet
    names = ["hit", "missed", "late", "early_release", "early_onset"]
    tints = {n: _rgb(report["tints"][n]) for n in names}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            assert np.abs(tints[a] - tints[b]).sum() >= 80, (a, b)
    background = _rgb(report["background"])
    for name, tint in tints.items():
        assert np.abs(tint - background).sum() >= 300, name


def test_the_grand_staff_brace_is_bold_and_filled(sheet):
    """N3: the brace at the strip's left edge is a heavy filled shape."""
    _, _, images = sheet
    gutter = images["baseline"][:, 0:29]
    bright = int((gutter.min(axis=2) > 150).sum())
    assert bright >= 1100, bright


def test_a_tied_continuation_head_takes_its_attacks_colour(sheet):
    """C4 (owner decision): attack and continuation heads share the status."""
    report, frames, images = sheet
    tied = [i for i in frames["tied"]["instances"]
            if i["head"] == "head_whole" and i["status"] == "missed"]
    assert len(tied) == 2, tied
    assert len({i["event_id"] for i in tied}) == 2  # two physical heads
    base, graded = images["tied-base"], images["tied"]
    tint = _rgb(report["tints"]["missed"])
    for item in tied:
        x, y = (int(round(v)) for v in item["position"])
        r = max(1, int(item["gap"] * .12))
        # The solid left and right rim of the whole head carries the tint.
        rim = graded[y - r:y + r + 1, int(x - item["gap"] * .8):int(x - item["gap"] * .55)]
        assert (np.abs(rim - tint).max(axis=2) <= 12).any(), item["event_id"]
