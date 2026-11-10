"""Actual framebuffer verification of note-status ink on authentic Verovio notation.

Godot renders the production NativeView with real Verovio assets, two physical
copies of the same source admitted through the view's own immutable stream
queue, and statuses delivered through the real ledger ingestion. Only PNGs,
public colors and the renderer's own reported instance geometry are measured.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image
import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = "tests/fixtures/note_status_probe.musicxml"
SHIFT = 48  # 0.5 beat at 96 px/beat between the "moved" frames


@pytest.fixture(scope="module")
def capture(tmp_path_factory):
    from scripts.check_native_verovio_overlay import AuditCase, fixture
    from test_native_fingering import _godot, _run_godot

    folder = tmp_path_factory.mktemp("note-status-framebuffer")
    data, _ = fixture(AuditCase("note-status", FIXTURE, 1, 2, "both"))
    payload = folder / "fixture.json"
    payload.write_text(json.dumps(data))
    result = _run_godot([*_godot(), "--path", str(ROOT / "godot"),
        "--rendering-method", "gl_compatibility", "--audio-driver", "Dummy",
        "--script", str(ROOT / "tests/godot/note_status_framebuffer.gd"),
        "--", str(payload), str(folder)], timeout=90)
    (folder / "godot.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "SCRIPT ERROR" not in result.stdout + result.stderr
    report = json.loads((folder / "status-report.json").read_text())
    images = {frame["name"]: np.asarray(Image.open(folder / frame["file"])
                                        .convert("RGB")).astype(int)
              for frame in report["frames"]}
    frames = {frame["name"]: frame for frame in report["frames"]}
    return report, frames, images


def _rgb(values):
    return np.array(values[:3], dtype=float) * 255


def _box(instance, pad=0, width=None):
    gap = instance["gap"]
    x, y = instance["position"]
    hx = (0.92 if instance["head"] == "head_whole" else 0.68) * gap + pad
    hy = 0.58 * gap + pad
    x0, y0 = int(np.floor(x - hx)), int(np.floor(y - hy))
    x1, y1 = int(np.ceil(x + hx)) + 1, int(np.ceil(y + hy)) + 1
    if width is not None:
        x0, x1 = max(0, x0), min(width, x1)
    return max(0, x0), max(0, y0), x1, y1


def _colored(frame):
    return [item for item in frame["instances"] if item["status"] != "unplayed"]


def _on_screen(instance, width):
    x0, _, x1, _ = _box(instance, 3, width)
    return x1 > x0


def _interior(instance, report, base, graded):
    """Fully inked head pixels away from stems: must become the exact tint."""
    x0, y0, x1, y1 = _box(instance, 0, base.shape[1])
    gap = instance["gap"]
    cx, cy = instance["position"]
    ys, xs = np.mgrid[y0:y1, x0:x1]
    inner = ((xs - cx) / (0.42 * gap)) ** 2 + ((ys - cy) / (0.36 * gap)) ** 2 <= 1
    ink = _rgb(report["ink"])
    full = (np.abs(base[y0:y1, x0:x1] - ink).max(axis=2) <= 8) & inner
    tint = _rgb(report["tints"][instance["status"]])
    tinted = (np.abs(graded[y0:y1, x0:x1] - tint).max(axis=2) <= 8) & full
    return int(full.sum()), int(tinted.sum())


def _edge_error(instance, frame, report, base, graded):
    """Deviation from a perfect in-place recolor b(1-a)+tint*a of the head.

    Coverage a comes from the untouched baseline. A white contour left under
    or around the colored head, a doubled paint, or a mask offset all raise
    this error; the faint glow alone stays small. Staff-line rows, stems and
    pixels nearer to another head are not modelled and are excluded.
    """
    bg, ink = _rgb(report["background"]), _rgb(report["ink"])
    tint = _rgb(report["tints"][instance["status"]])
    gap = instance["gap"]
    cx, cy = instance["position"]
    x0, y0, x1, y1 = _box(instance, 3, base.shape[1])
    b, g = base[y0:y1, x0:x1], graded[y0:y1, x0:x1]
    axis = ink - bg
    a = np.clip(((b - bg) * axis).sum(axis=2) / (axis * axis).sum(), 0, 1)
    predicted = bg * (1 - a[..., None]) + tint * a[..., None]
    error = np.abs(g - predicted).max(axis=2)
    keep = np.ones(a.shape, bool)
    staff = _rgb(report["background"]) * .52 + ink * .48
    rows = np.where((np.abs(base - staff).max(axis=2) <= 30).mean(axis=1) > .5)[0]
    for row in rows:
        for d in (-1, 0, 1):
            if y0 <= row + d < y1:
                keep[row + d - y0, :] = False
    inkish = np.abs(base - ink).max(axis=2) <= 40
    reach = int(1.6 * gap)
    stem = ((inkish[max(0, y0 - reach):y0, x0:x1].sum(axis=0) >= 1.3 * gap) |
            (inkish[y1:y1 + reach, x0:x1].sum(axis=0) >= 1.3 * gap))
    stem = stem | np.roll(stem, 1) | np.roll(stem, -1)
    keep[:, stem] = False
    ys, xs = np.mgrid[y0:y1, x0:x1]
    mine = (xs - cx) ** 2 + ((ys - cy) / .8) ** 2
    for other in frame["instances"]:
        ox, oy = other["position"]
        if other is instance or abs(ox - cx) > 2 * gap or abs(oy - cy) > 2 * gap:
            continue
        keep &= mine <= (xs - ox) ** 2 + ((ys - oy) / .8) ** 2
    sample = error[keep & (a > .05)]
    return sample, a


def test_every_status_event_is_applied_to_two_physical_copies(capture):
    report, frames, _ = capture
    assert report["outcomes"] and set(report["outcomes"]) == {"applied"}
    takes = {item["take_key"] for item in frames["graded"]["instances"]}
    assert takes == {report["take_a"], report["take_b"]}
    statuses = {item["status"] for item in _colored(frames["graded"])}
    assert statuses == {"hit", "missed", "late", "early_release", "early_onset"}
    heads = {item["head"] for item in _colored(frames["graded"])}
    assert heads == {"head_black", "head_half", "head_whole"}
    sources = {item["source"] for item in _colored(frames["graded"])}
    assert {"note", "chord"} <= sources, "composite note and chord artwork are recolored"


def test_unplayed_notation_is_pixel_identical(capture):
    report, frames, images = capture
    for name, base_name in (("graded", "baseline"), ("graded-moved", "baseline-moved")):
        graded, base = images[name], images[base_name]
        changed = np.abs(graded - base).max(axis=2) > 0
        allowed = np.zeros(changed.shape, bool)
        for item in _colored(frames[name]):
            x0, y0, x1, y1 = _box(item, 3, graded.shape[1])
            allowed[y0:y1, x0:x1] = True
        assert changed.any()
        # No ring, badge, halo or other detached mark anywhere else.
        assert not (changed & ~allowed).any(), int((changed & ~allowed).sum())
        for item in frames[name]["instances"]:
            if item["status"] == "unplayed" and _on_screen(item, graded.shape[1]):
                x0, y0, x1, y1 = _box(item, 3, graded.shape[1])
                region = changed[y0:y1, x0:x1]
                near_colored = any(
                    abs(o["position"][0] - item["position"][0]) < 2 * item["gap"] and
                    abs(o["position"][1] - item["position"][1]) < 2 * item["gap"]
                    for o in _colored(frames[name]))
                if not near_colored:
                    assert not region.any(), item["event_id"]


def test_status_core_is_the_opaque_exact_tint(capture):
    report, frames, images = capture
    for item in _colored(frames["graded"]):
        if not _on_screen(item, images["graded"].shape[1]):
            continue
        full, tinted = _interior(item, report, images["baseline"], images["graded"])
        assert full > 0 and tinted == full, (item["status"], item["head"], full, tinted)


def test_recolor_replaces_the_white_head_without_a_doubled_contour(capture):
    report, frames, images = capture
    measured = 0
    for item in _colored(frames["graded"]):
        if not _on_screen(item, images["graded"].shape[1]):
            continue
        sample, _ = _edge_error(item, frames["graded"], report,
                                images["baseline"], images["graded"])
        assert sample.size > 100, item["event_id"]
        assert sample.mean() <= 6.0, (item["status"], item["head"], sample.mean())
        assert np.percentile(sample, 95) <= 32.0, (
            item["status"], item["head"], np.percentile(sample, 95))
        measured += 1
    assert measured >= 10


def test_glow_is_extremely_subtle_and_follows_the_notehead_mask(capture):
    report, frames, images = capture
    base, graded = images["baseline"], images["graded"]
    bg = _rgb(report["background"])
    glowing = 0
    for item in _colored(frames["graded"]):
        if not _on_screen(item, base.shape[1]):
            continue
        x0, y0, x1, y1 = _box(item, 3, base.shape[1])
        b, g = base[y0:y1, x0:x1], graded[y0:y1, x0:x1]
        _, coverage = _edge_error(item, frames["graded"], report, base, graded)
        near = coverage > .05
        for _ in range(3):  # within 3 px of the authentic head ink
            near = near | np.roll(near, 1, 0) | np.roll(near, -1, 0) | \
                np.roll(near, 1, 1) | np.roll(near, -1, 1)
        changed = np.abs(g - b).max(axis=2) > 0
        assert not (changed & ~near).any(), "glow detached from the head mask"
        background = np.abs(b - bg).max(axis=2) <= 12
        lift = np.abs(g - b).max(axis=2)[background & changed]
        if lift.size:
            glowing += 1
            assert lift.max() <= 40, (item["status"], int(lift.max()))
    assert glowing >= 8, "colored heads carry a tiny contour glow"


def test_hollow_heads_stay_hollow(capture):
    _, frames, images = capture
    hollow = 0
    for item in _colored(frames["graded"]):
        if item["head"] == "head_black" or not _on_screen(item, images["graded"].shape[1]):
            continue
        # The hole (background or the staff line through it) is untouched.
        x, y = (int(round(v)) for v in item["position"])
        r = max(1, int(item["gap"] * .12))
        assert np.array_equal(images["graded"][y - r:y + r + 1, x - r:x + r + 1],
                              images["baseline"][y - r:y + r + 1, x - r:x + r + 1]), (
            item["head"], item["status"])
        hollow += 1
    assert hollow >= 4


def test_repeated_passage_copies_keep_independent_statuses(capture):
    report, frames, images = capture
    graded = images["graded"]
    by_take = {}
    for item in frames["graded"]["instances"]:
        by_take.setdefault(item["event_id"], {})[item["take_key"]] = item
    tints = {name: _rgb(value) for name, value in report["tints"].items()}

    def ink_at(item):
        x0, y0, x1, y1 = _box(item, 0, graded.shape[1])
        _, tinted = _interior(item, report, images["baseline"], graded)
        return tinted

    repeated = [copies for copies in by_take.values() if len(copies) == 2]
    assert len(repeated) >= 3, "the same source notes are on screen twice"
    contrasting = 0
    for copies in repeated:
        first, second = copies[report["take_a"]], copies[report["take_b"]]
        if first["status"] != second["status"]:
            contrasting += 1
            for item in (first, second):
                if item["status"] != "unplayed":
                    assert ink_at(item) > 0
        if second["status"] == "unplayed":
            x0, y0, x1, y1 = _box(second, 0, graded.shape[1])
            assert np.array_equal(graded[y0:y1, x0:x1],
                                  images["baseline"][y0:y1, x0:x1])
    assert contrasting >= 3
    first_e4 = [c for c in repeated if c[report["take_a"]]["status"] == "hit"
                and c[report["take_b"]]["status"] == "missed"]
    assert first_e4, "one source note is mint in one copy and coral in the next"
    assert tints["hit"].tolist() != tints["missed"].tolist()


def test_status_ink_moves_with_its_strip_and_never_repaints_per_frame(capture):
    report, frames, images = capture
    assert report["paints"]["graded"] > report["paints"]["before"]
    assert report["paints"]["moved"] == report["paints"]["graded"], (
        "scrolling must not repaint status ink")
    delta = images["graded"] - images["baseline"]
    moved = images["graded-moved"] - images["baseline-moved"]
    width = delta.shape[1]
    # The status ink difference translates exactly with the source strip.
    assert np.array_equal(moved[:, :width - SHIFT], delta[:, SHIFT:])


def test_status_pixels_stay_inside_their_own_strip_clip(capture):
    report, frames, images = capture
    graded, base = images["graded"], images["baseline"]
    changed = np.abs(graded - base).max(axis=2) > 0
    inside = np.zeros(changed.shape[1], bool)
    for item in frames["graded"]["instances"]:
        assert item["take_key"] in (report["take_a"], report["take_b"])
        left, right = item["clip_x"]
        assert left < right, "every projected instance carries its strip clip"
        if item["status"] != "unplayed":
            inside[max(0, int(np.floor(left))):max(0, int(np.ceil(right)))] = True
    assert not changed[:, ~inside].any()
    # Strips are cut only where no authentic notehead or connector ink is split
    # (9dbd28ed, e295407f), so every recolored head lies wholly inside the one
    # strip that owns it and is tinted completely in its own clip.
    colored = _colored(frames["graded"])
    assert colored
    for item in colored:
        left, right = item["clip_x"]
        half = (0.92 if item["head"] == "head_whole" else 0.68) * item["gap"]
        assert left <= item["position"][0] - half and item["position"][0] + half <= right, (
            "a recolored head straddles a clipped strip boundary", item)
        full, tinted = _interior(item, report, base, graded)
        assert full > 0 and tinted == full
        if item["head"] != "head_black":
            continue  # a hollow head's centre columns are its hole
        x = int(round(item["position"][0]))
        y0, y1 = (int(round(item["position"][1] + d * item["gap"])) for d in (-.2, .2))
        tint = _rgb(report["tints"][item["status"]])
        for column in (x - 2, x - 1, x, x + 1):
            assert (np.abs(graded[y0:y1, column] - tint).max(axis=1) <= 8).all()


def test_ungraded_preview_shows_original_notation(capture):
    _, _, images = capture
    assert np.array_equal(images["suppressed"], images["baseline-moved"])
