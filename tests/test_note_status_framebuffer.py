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
    # The native painter deliberately fills hollow glyph apertures with a
    # translucent status tint. Retain its authentic masks so contour checks
    # can distinguish that fill from leftover white source head ink, even when
    # a staff rule splits the aperture in the baseline screenshot.
    report["_hollow_masks"] = {
        head: {
            "alpha": np.asarray(Image.open(folder / filename).convert("RGBA"))[:, :, 3] / 255.0,
            "bounds": tuple(data["assets"]["native_glyphs"][head]["bounds"]),
        }
        for head, filename in report["hollow_interior_files"].items()
    }
    # Exact alpha of the production head paint (the whole-note source template
    # or the extracted authentic head-only pixels for composite artwork).
    # Staff-rule color in the baseline is not usable as a head alpha mask.
    report["_source_head_masks"] = {
        key: {
            "alpha": np.asarray(Image.open(folder / entry["file"]).convert("RGBA"))[:, :, 3] / 255.0,
            "bounds": tuple(entry["bounds"]),
            "centered": bool(entry["centered"]),
        }
        for key, entry in report["source_head_masks"].items()
    }
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
    # Display-scale heads are antialiased; a pixel at the rim of a hollow
    # head's aperture may mix a few percent of its neighbour (seen: 11/255).
    # Surviving white source ink would be 100+ away from any status tint.
    tinted = (np.abs(graded[y0:y1, x0:x1] - tint).max(axis=2) <= 16) & full
    return int(full.sum()), int(tinted.sum())


def _grow(mask, steps):
    for _ in range(steps):
        mask = mask | np.roll(mask, 1, 0) | np.roll(mask, -1, 0) | \
            np.roll(mask, 1, 1) | np.roll(mask, -1, 1)
    return mask


def _hollow_fill_mask(instance, report, origin, shape):
    """Project the production hollow-head fill alpha to this framebuffer crop.

    Its source is Godot's actual glyph image, not a hole guessed from the
    composited baseline: staff lines can cross the aperture, especially on
    whole notes that lie on a rule.
    """
    asset = report["_hollow_masks"].get(instance["head"])
    if asset is None:
        return np.zeros(shape, dtype=bool)
    alpha = asset["alpha"]
    bounds = asset["bounds"]
    cx, cy = instance["position"]
    cx += _window_snap(instance)
    scale = float(instance["gap"]) / 250.0
    left = cx - float(bounds[2]) * scale * .5
    top = cy + float(bounds[1]) * scale
    width, height = float(bounds[2]) * scale, float(bounds[3]) * scale
    y0, x0 = origin
    ys, xs = np.mgrid[y0:y0 + shape[0], x0:x0 + shape[1]]
    u = (xs + .5 - left) / width * alpha.shape[1]
    v = (ys + .5 - top) / height * alpha.shape[0]
    inside = (u >= 0) & (v >= 0) & (u < alpha.shape[1]) & (v < alpha.shape[0])
    ix = np.clip(u.astype(int), 0, alpha.shape[1] - 1)
    iy = np.clip(v.astype(int), 0, alpha.shape[0] - 1)
    # One-pixel margin absorbs Godot's bilinear texture filtering. Only the
    # deliberately filled aperture is excluded; the outer contour stays
    # subject to the original strict white-ink/doubled-edge checks.
    return _grow(inside & (alpha[iy, ix] > .03), 1)


def _window_snap(instance):
    """Sub-pixel distance between a head's reported position and its ink.

    Reported positions lie on the exact world axis. The strip that owns the
    head is clipped by a Control window at ``clip_x[0]``, and Godot draws a
    Control at whole pixels: its canvas transform is rounded when rendered
    (``(origin + 0.025).round()``), carrying the strip's ink and its status
    ink with it. A window at the integer staff gutter does not move; a later
    strip's window at e.g. 467.57 is drawn at 468, +0.43 px.
    """
    left = float(instance["clip_x"][0])
    return float(np.floor(left + 0.025 + 0.5)) - left


def _source_head_alpha(instance, report, origin, shape, scale=1.0, snapped=True):
    """Reproject the exact engraved texture alpha in its *original* rectangle.

    The whole-note template differs from the font glyph. More importantly,
    staff rules beneath a hollow head are part of the baseline framebuffer
    but NOT part of its recolored source mask.
    """
    if snapped:
        shift = _window_snap(instance)
        instance = dict(instance,
                        position=[instance["position"][0] + shift, instance["position"][1]],
                        anchor=[instance["anchor"][0] + shift, instance["anchor"][1]])
    key = "{}|{}|{}|{}".format(
        instance["source"], instance.get("template", ""),
        instance.get("head_index", 0), instance["head"])
    source = report["_source_head_masks"][key]
    alpha = source["alpha"]
    box = source["bounds"]
    scale_px = float(instance["gap"]) / 250.0
    anchor = instance["position"] if source["centered"] else instance["anchor"]
    left = anchor[0] + (-(float(box[2]) * .5) if source["centered"]
                         else float(box[0])) * scale_px
    top = anchor[1] + float(box[1]) * scale_px
    width, height = float(box[2]) * scale_px, float(box[3]) * scale_px
    # Godot grows the actual source texture about the engraved head centre,
    # without moving the source/template anchor or changing any note spacing.
    cx, cy = instance["position"]
    left = cx + (left - cx) * scale
    top = cy + (top - cy) * scale
    width *= scale
    height *= scale
    y0, x0 = origin
    ys, xs = np.mgrid[y0:y0 + shape[0], x0:x0 + shape[1]]
    # Center-sampled texture coordinates, using bilinear filtering like the
    # native draw_texture_rect call. Pixels outside the destination rect have
    # no source coverage, even where sampler addressing clamps to an edge.
    u = (xs + .5 - left) * alpha.shape[1] / width
    v = (ys + .5 - top) * alpha.shape[0] / height
    inside = (u >= 0) & (v >= 0) & (u < alpha.shape[1]) & (v < alpha.shape[0])
    u, v = u - .5, v - .5
    ix0, iy0 = np.floor(u).astype(int), np.floor(v).astype(int)
    fx, fy = u - ix0, v - iy0
    ix1, iy1 = ix0 + 1, iy0 + 1
    ix0, ix1 = np.clip(ix0, 0, alpha.shape[1] - 1), np.clip(ix1, 0, alpha.shape[1] - 1)
    iy0, iy1 = np.clip(iy0, 0, alpha.shape[0] - 1), np.clip(iy1, 0, alpha.shape[0] - 1)
    sampled = (
        alpha[iy0, ix0] * (1 - fx) * (1 - fy) +
        alpha[iy0, ix1] * fx * (1 - fy) +
        alpha[iy1, ix0] * (1 - fx) * fy +
        alpha[iy1, ix1] * fx * fy
    )
    return np.where(inside, sampled, 0.0)


def _recolored_pixel_prediction(baseline, source_alpha, source_ink, tint):
    # Subtract the exact original notehead ink and add the tint with the same
    # coverage. Never subtract the underlying staff rule from the framebuffer.
    return np.clip(baseline + (tint - source_ink) * source_alpha[..., None], 0, 255)


def _two_pass_glow_prediction(base, tint, outer_alpha, inner_alpha):
    """Godot MIX compositor: two low-opacity source-alpha glow layers."""
    after_outer = base + (tint - base) * outer_alpha[..., None]
    return after_outer + (tint - after_outer) * inner_alpha[..., None]


def test_glow_prediction_uses_both_source_alpha_layers():
    """Opaque status contours remain tint colored; nearby pixels glow softly."""
    baseline = np.array([[[11., 39., 34.], [238., 245., 241.]]])
    tint = np.array([241., 121., 120.])
    outer = np.array([[.045, .045]])
    inner = np.array([[.105, .105]])
    after = _two_pass_glow_prediction(baseline, tint, outer, inner)
    assert np.all(after[0, 0] > baseline[0, 0])
    assert np.all(np.abs(after[0, 1] - tint) < np.abs(baseline[0, 1] - tint))


def test_source_alpha_model_preserves_staff_ink_and_rejects_ghosts():
    """A whole note over a staff line must keep the rule, not count it as ghost ink."""
    bg = np.array([11.0, 39.0, 34.0])
    ink = np.array([238.0, 245.0, 241.0])
    tint = np.array([240.0, 143.0, 203.0])
    rule = np.array([[0.0, .48, .48], [.48, .48, 0.0]])
    alpha = np.array([[.0, .0, .7], [1.0, .2, .0]])
    underlying = bg * (1 - rule[..., None]) + ink * rule[..., None]
    baseline = underlying * (1 - alpha[..., None]) + ink * alpha[..., None]
    correct = underlying * (1 - alpha[..., None]) + tint * alpha[..., None]
    prediction = _recolored_pixel_prediction(baseline, alpha, ink, tint)
    np.testing.assert_allclose(prediction, correct, atol=1e-10)
    assert np.abs(baseline[0, 1] - prediction[0, 1]).max() == 0
    assert np.abs(baseline[1, 0] - prediction[1, 0]).max() > 6


def _edge_error(instance, frame, report, base, graded):
    """Deviation from the true in-place recolor of authentic notehead ink.

    Source alpha a comes from the exact Godot texture and destination rectangle.
    The background can include a staff rule, so estimate predicted graded
    pixels from the baseline b: b + (tint - source_ink) * a. Inferring a from
    b - the flat stage background incorrectly labels underlying staff rules
    as unmodified white notehead contours, especially for hollow whole notes.
    This still fails on any surviving original outline or doubled tint.
    """
    bg, ink = _rgb(report["background"]), _rgb(report["ink"])
    tint = _rgb(report["tints"][instance["status"]])
    gap = instance["gap"]
    cx, cy = instance["position"]
    x0, y0, x1, y1 = _box(instance, 3, base.shape[1])
    b, g = base[y0:y1, x0:x1], graded[y0:y1, x0:x1]
    a = _source_head_alpha(instance, report, (y0, x0), b.shape[:2])
    predicted = _recolored_pixel_prediction(b, a, ink, tint)
    # Production paints TWO small, authentic source-alpha MIX layers after
    # the subtract/add recolor. The contour assertion compares against that
    # actual final intent, rather than treating deliberate glow as stray ink.
    # No contour pixels are removed and the 6.0/32.0 error limits are unchanged.
    glow = report["glow"]
    outer = _source_head_alpha(instance, report, (y0, x0), b.shape[:2],
                               scale=float(glow["outer_scale"])) * float(glow["outer_alpha"])
    inner = _source_head_alpha(instance, report, (y0, x0), b.shape[:2],
                               scale=float(glow["inner_scale"])) * float(glow["inner_alpha"])
    predicted = _two_pass_glow_prediction(predicted, tint, outer, inner)
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
    if instance["head"] != "head_black":
        # C5: the hollow aperture has its own MIX-blended fill pass.
        # The untouched source screenshot is not enough to infer its mask:
        # staff ink may run through the aperture and split the visible hole.
        # Exclude exactly the native painter's fill region while continuing
        # to verify its outside ink contour for residual white/double edges.
        keep &= ~_hollow_fill_mask(instance, report, (y0, x0), a.shape)
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


def test_projected_standalone_heads_keep_their_exact_engraving_anchor(capture):
    """Screen-space metadata must use the same translation as retained ink."""
    _, frames, _ = capture
    observed = 0
    for frame in frames.values():
        for item in frame["instances"]:
            if item["source"] != "note":
                continue
            np.testing.assert_allclose(item["anchor"], item["position"], atol=1e-5,
                                       err_msg=item["event_id"])
            observed += 1
    assert observed >= 4


def test_authentic_source_alpha_covers_each_visible_colored_head(capture):
    """A zero/offscreen mask must fail before pixel or glow comparisons."""
    report, frames, images = capture
    for item in _colored(frames["graded"]):
        if not _on_screen(item, images["graded"].shape[1]):
            continue
        x0, y0, x1, y1 = _box(item, 3, images["graded"].shape[1])
        coverage = _source_head_alpha(item, report, (y0, x0), (y1 - y0, x1 - x0))
        assert (coverage > .05).sum() > 100, (
            item["event_id"], item["source"], item["head"],
            item["position"], item["anchor"], float(coverage.max()))


def test_recolor_replaces_the_white_head_without_a_doubled_contour(capture):
    report, frames, images = capture
    measured = 0
    for item in _colored(frames["graded"]):
        if not _on_screen(item, images["graded"].shape[1]):
            continue
        sample, _ = _edge_error(item, frames["graded"], report,
                                images["baseline"], images["graded"])
        assert sample.size > 100, item["event_id"]
        assert sample.mean() <= 6.0, (item["event_id"], item["status"], item["head"], sample.mean())
        assert np.percentile(sample, 95) <= 32.0, (
            item["status"], item["head"], np.percentile(sample, 95))
        measured += 1
    assert measured >= 10


def test_ink_follows_its_pixel_snapped_strip_window_not_the_exact_axis(capture):
    """The recolor model is only valid with the strip window's pixel snap.

    Measured on the baseline alone (no status ink involved): the authentic
    head alpha placed at the snapped window explains the photographed head
    better than the same alpha at the unsnapped reported position, for every
    solid head whose window is drawn at least 0.3 px away from its axis.
    """
    report, frames, images = capture
    base = images["baseline"].astype(float)
    bg, ink = _rgb(report["background"]), _rgb(report["ink"])
    moved = 0
    for item in _colored(frames["graded"]):
        if item["head"] != "head_black" or item["source"] == "chord" \
                or not _on_screen(item, base.shape[1]):
            continue
        shift = _window_snap(item)
        assert abs(shift) <= 0.5 + 1e-6
        if abs(shift) < 0.3:
            continue
        x0, y0, x1, y1 = _box(item, 3, base.shape[1])
        crop = base[y0:y1, x0:x1]
        photographed = ((crop - bg) / (ink - bg)).mean(axis=2)
        errors = {}
        for snapped in (True, False):
            alpha = _source_head_alpha(item, report, (y0, x0), crop.shape[:2],
                                       snapped=snapped)
            considered = (alpha > .02) | (photographed > .02)
            errors[snapped] = float(np.abs(alpha - photographed)[considered].mean())
        assert errors[True] < errors[False], (item["event_id"], shift, errors)
        moved += 1
    assert moved >= 2, "the probe has heads in strips whose window is snapped"



def test_standalone_whole_note_recolor_uses_original_engraved_artwork(capture):
    """A head-only Verovio template must not be replaced by a cutout guess."""
    report, frames, _ = capture
    whole = [item for item in _colored(frames["graded"])
             if item["head"] == "head_whole"]
    assert whole and any(item["status"] == "early_onset" for item in whole)
    assert all(item["source"] == "note" for item in whole)
    glyphs = (ROOT / "godot/notation/native/glyphs.gd").read_text()
    assert 'source == "note" and head == "head_whole" and key == "whole"' in glyphs
    assert 'return paint_note(canvas,"whole",true,point.x,point.y,gap,color)' in glyphs


def test_original_white_whole_note_contour_would_still_fail_recolor_check(capture):
    """Masking the intentional interior must not mask doubled source edges."""
    report, frames, images = capture
    item = next(item for item in _colored(frames["graded"])
                if item["head"] == "head_whole" and item["status"] == "early_onset")
    assert _on_screen(item, images["graded"].shape[1])
    ghosted = images["graded"].copy()
    x0, y0, x1, y1 = _box(item, 3, ghosted.shape[1])
    ghosted[y0:y1, x0:x1] = images["baseline"][y0:y1, x0:x1]
    sample, _ = _edge_error(item, frames["graded"], report, images["baseline"], ghosted)
    assert sample.size > 100 and sample.mean() > 6.0


def _status_ink_reach(item, report, origin, shape):
    """Pixels within 3 px of one colored head's authentic ink or hollow fill."""
    near = _source_head_alpha(item, report, origin, shape) > .05
    for _ in range(3):  # within 3 px of the authentic head ink
        near = near | np.roll(near, 1, 0) | np.roll(near, -1, 0) | \
            np.roll(near, 1, 1) | np.roll(near, -1, 1)
    # The production C5 fill is made from the original glyph's enclosed
    # alpha, not a hole inferred from a source template. A stem or a staff
    # rule can open/split the apparent hole in the baseline; use the exact
    # exported fill pixels and keep every other changed pixel accountable.
    interior = (_hollow_fill_mask(item, report, origin, shape)
                if item["head"] != "head_black" else np.zeros(shape, bool))
    return near | interior, interior


def _detached_glow(item, frame, report, base, graded):
    """Changed pixels of this head's crop that no colored head accounts for.

    Chord heads a second or a third apart share part of each other's crop.
    The neighbour's own recolored ink is status ink bound to ITS authentic
    mask, so every colored head whose mask reaches into the crop is modelled
    with the same 3 px rule; nothing else may change.
    """
    x0, y0, x1, y1 = _box(item, 3, base.shape[1])
    b, g = base[y0:y1, x0:x1], graded[y0:y1, x0:x1]
    shape = b.shape[:2]
    accounted, interior = _status_ink_reach(item, report, (y0, x0), shape)
    neighbours = np.zeros(shape, bool)
    gap = item["gap"]
    for other in _colored(frame):
        if other is item or abs(other["position"][0] - item["position"][0]) > 3 * gap \
                or abs(other["position"][1] - item["position"][1]) > 3 * gap:
            continue
        neighbours = neighbours | _status_ink_reach(other, report, (y0, x0), shape)[0]
    changed = np.abs(g - b).max(axis=2) > 0
    return {"detached": changed & ~(accounted | neighbours), "changed": changed,
            "interior": interior, "neighbours": neighbours, "base": b, "graded": g}


def test_glow_is_extremely_subtle_and_follows_the_notehead_mask(capture):
    report, frames, images = capture
    base, graded = images["baseline"], images["graded"]
    bg = _rgb(report["background"])
    glowing = 0
    shared = 0
    for item in _colored(frames["graded"]):
        if not _on_screen(item, base.shape[1]):
            continue
        crop = _detached_glow(item, frames["graded"], report, base, graded)
        detached, changed, interior = crop["detached"], crop["changed"], crop["interior"]
        b, g = crop["base"], crop["graded"]
        shared += bool((changed & crop["neighbours"]).any())
        assert not detached.any(), (
            "glow detached from authentic notehead/fill mask",
            item["event_id"], item["status"], item["head"],
            item["source"], item.get("template", ""),
            int(detached.sum()))
        # A neighbouring chord head's opaque core is not this head's glow.
        background = (np.abs(b - bg).max(axis=2) <= 12) & ~interior & ~crop["neighbours"]
        lift = np.abs(g - b).max(axis=2)[background & changed]
        if lift.size:
            glowing += 1
            assert lift.max() <= 40, (item["status"], int(lift.max()))
    assert glowing >= 8, "colored heads carry a tiny contour glow"
    assert shared >= 2, "the probe includes chord heads that share a crop"


def test_stray_mark_beside_a_colored_chord_head_is_still_detached(capture):
    """Accounting for a neighbouring chord head must not excuse other ink."""
    report, frames, images = capture
    base = images["baseline"]
    chord = [item for item in _colored(frames["graded"])
             if item["source"] == "chord" and _on_screen(item, base.shape[1])]
    assert len(chord) >= 2, "the probe needs two colored heads of one chord"
    item = chord[0]
    crop = _detached_glow(item, frames["graded"], report, base, images["graded"])
    changed = crop["changed"]
    assert not crop["detached"].any()
    x0, y0, x1, y1 = _box(item, 3, base.shape[1])
    accounted = changed.copy()
    for head in chord:
        accounted |= _status_ink_reach(head, report, (y0, x0), changed.shape)[0]
    free = np.argwhere(~accounted)
    assert free.size, "no unaccounted pixel in the crop to mutate"
    # One tinted pixel in the crop that neither chord head's mask reaches.
    row, column = free[0]
    marked = images["graded"].copy()
    marked[y0 + row, x0 + column] = _rgb(report["tints"][item["status"]])
    stray = _detached_glow(item, frames["graded"], report, base, marked)["detached"]
    assert stray[row, column] and int(stray.sum()) == 1



def test_hollow_heads_are_tinted_softly_inside_their_own_mask(capture):
    """C5: half and whole heads get a soft interior tint (never a ring)."""
    report, frames, images = capture
    hollow = 0
    for item in _colored(frames["graded"]):
        if item["head"] == "head_black" or not _on_screen(item, images["graded"].shape[1]):
            continue
        x, y = (int(round(v)) for v in item["position"])
        r = max(1, int(item["gap"] * .12))
        b = images["baseline"][y - r:y + r + 1, x - r:x + r + 1].astype(float)
        g = images["graded"][y - r:y + r + 1, x - r:x + r + 1].astype(float)
        tint = _rgb(report["tints"][item["status"]])
        # Moved toward the status colour, softly: between 20% and 75% of the way.
        along = ((g - b) * (tint - b)).sum(axis=2) / np.maximum(
            ((tint - b) ** 2).sum(axis=2), 1.0)
        assert .2 <= along.mean() <= .75, (item["head"], item["status"], along.mean())
        # No ring: nothing changed farther than 3 px outside the head's own ink.
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
