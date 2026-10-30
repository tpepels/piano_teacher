"""Causal source-slur ownership using actual unsuppressed/suppressed PNGs.

A renderer-reported control *key* is only a proposal. Independent original
MusicXML endpoint registration, physical pixels, stable baselines, curvature,
attachments, and source-exclusive changed ink must all agree. This complements
the unsuppressed connected-curve oracle for crossed contours; it cannot pass
on an atlas drawing, a missing control, or a screenshot that drifts over time.
"""
from __future__ import annotations

from pathlib import Path
import json

import numpy as np
from PIL import Image

from .pixel_ink import bright


def _pixels(folder, filename):
    # Do not let an untrusted control manifest read outside the capture root.
    if Path(filename).name != filename or not filename.endswith(".png"):
        raise ValueError("Invalid control PNG filename")
    with Image.open(folder / filename) as image:
        return np.asarray(image.convert("RGB"), dtype=np.int16)


def _runs(mask):
    ys, xs = np.nonzero(mask)
    out = []
    for y in np.unique(ys):
        columns = xs[ys == y]
        for part in np.split(columns, np.flatnonzero(np.diff(columns) > 1) + 1):
            out.append([int(y), int(part[0]), int(part[-1]) + 1])
    return out


def measure_slur_interventions(xml, written, pairs, folder):
    """Return physically verified per-source slur differences, or nothing.

    All expected source slurs must have unique controls, because a missing
    competing slur makes the exclusivity comparison unsound. Source ties do
    not need suppression; they remain under the unsuppressed curve verifier.
    """
    from .symbol_pixel_proof import (PLAYHEAD, _connector_head,
                                     _connector_shift)

    folder = Path(folder)
    report_file = folder / "native-overlay-report.json"
    if not report_file.is_file():
        return {}
    try:
        report = json.loads(report_file.read_text())
        controls = report.get("slur_difference_controls", [])
        controls_at = report.get("slur_difference_frames", [])
        slurs = [p for p in pairs if p["construct"] == "slur"
                 and not p.get("reason") and len(p["notes"]) == 2]
        keys = ["|".join(n.get("id") or n["source"]["id"] for n in p["notes"])
                for p in slurs]
        if not keys or len(set(keys)) != len(keys):
            return {}
        if len(controls) != len(keys) or len(controls_at) != 1:
            return {}
        lookup = {row["key"]: row for row in controls}
        if len(lookup) != len(keys) or set(lookup) != set(keys):
            return {}
        meta = controls_at[0]
        baseline = meta["baseline_file"]
        if any(row.get("baseline_file") != baseline for row in controls):
            return {}
        base = _pixels(folder, baseline)
        repeat = _pixels(folder, meta["repeat_file"])
        restored = _pixels(folder, meta["restored_file"])
        if base.shape != repeat.shape or base.shape != restored.shape or (
                np.max(np.abs(base-repeat)) > 2 or
                np.max(np.abs(base-restored)) > 2):
            return {}
        clock = float(meta["clock"])
        if abs(float(baseline.removeprefix("native-").removesuffix(".png"))-clock) > .00001:
            return {}
        with Image.open(folder / baseline) as image:
            common = image.convert("RGB")
        luminosity = bright(common)
        anchor_cache, shifts, masks, shapes = {}, {}, {}, {}
        for pair, key in zip(slurs, keys):
            control = lookup[key]
            other = _pixels(folder, control["file"])
            if other.shape != base.shape:
                return {}
            mask = np.max(np.abs(base-other), axis=2) >= 20
            ys, xs = np.nonzero(mask)
            if len(xs) < 30:
                return {}
            columns = np.flatnonzero(mask.any(axis=0))
            if len(columns) < 2 or columns[-1]-columns[0] < 35 or (
                    np.diff(columns).max() > 3):
                return {}
            centers = np.array([np.median(np.flatnonzero(mask[:, x]))
                                for x in columns])
            chord = np.linspace(centers[0], centers[-1], len(centers))
            sag = float(np.max(np.abs(centers-chord)))
            heads = []
            for note in pair["notes"]:
                sid = note["source"]["id"]
                if sid not in anchor_cache:
                    onset = float(note["beat"])
                    source_file = folder / f"native-{onset:.2f}.png"
                    with Image.open(source_file) as img:
                        source = img.convert("RGB")
                    anchor = _connector_head(source, written, note,
                                             source.width*PLAYHEAD)
                    if anchor is None:
                        return {}
                    if onset not in shifts:
                        shifts[onset] = (
                            {"shift": 0} if abs(onset-clock) < 1e-8
                            else _connector_shift(common, source))
                    shift = shifts[onset]
                    if shift is None:
                        return {}
                    found = _connector_head(
                        common, written, note, anchor["x"]+shift["shift"])
                    if found is None:
                        return {}
                    anchor_cache[sid] = found
                heads.append(anchor_cache[sid])
            gap = min(head["gap"] for head in heads)
            if sag < .20*gap or max(int(mask[:, x].sum()) for x in columns) > .65*gap:
                return {}
            endpoints = ((int(columns[0]), float(centers[0])),
                         (int(columns[-1]), float(centers[-1])))
            for (x, y), head in zip(endpoints, heads):
                if abs(x-head["x"]) > .8*gap:
                    return {}
                l, t, r, b = head["bbox"]
                distance = float(np.hypot(max(l-x, 0, x-r), max(t-y, 0, y-b)))
                if distance <= 1.2*gap:
                    continue
                first, last = sorted((round(y), round(head["y"])))
                if last-first < .9*gap:
                    return {}
                if not any(
                    abs(column-x) < .65*gap and
                    float(np.mean(luminosity[first:last+1, column])) >= .88
                    for column in range(max(0,int(l)-8),
                                        min(luminosity.shape[1],int(r)+8))):
                    return {}
            masks[key] = mask
            shapes[key] = dict(heads=heads,changed_pixels=int(mask.sum()),
                               curvature_spaces=round(sag/gap,3))
        # Only pixels changed by this suppression and by NO other suppression
        # are source-exclusively attributable. The complete change mask must
        # already have passed source endpoint and curvature checks above.
        results = {}
        for key in keys:
            mask = masks[key]
            others = np.logical_or.reduce([other for other_key,other in masks.items()
                                           if other_key != key]) if len(keys)>1 else np.zeros_like(mask)
            exclusive = mask & ~others
            if int(exclusive.sum()) < 24:
                continue
            results[key] = dict(
                status="verified",
                reason="Stable source-specific slur suppression exposes curved, attached, exclusive native ink",
                method="causal-framebuffer-difference",
                frame=baseline,
                source_control=lookup[key]["file"],
                **shapes[key],
                exclusive_pixels=int(exclusive.sum()),
                pixel_runs=_runs(exclusive))
        return results
    except (OSError, KeyError, ValueError, TypeError, IndexError, AssertionError):
        return {}
