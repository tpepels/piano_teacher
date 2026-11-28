"""Offline motion-compensated analysis of actual production viewport frames."""

import argparse
import io
import json
import math
import struct
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
from visual_motion import scroll_velocity, strip_witnesses

MAX_EVIDENCE = 8


def rectangle(meta, key, shape):
    x, y, w, h = meta.get(key, (0, 0, 0, 0))
    height, width = shape
    return (max(0, round(x*width)), max(0, round(y*height)),
            min(width, round((x+w)*width)), min(height, round((y+h)*height)))


def shift(mask, dx):
    """Translate without wrapping ink around the viewport edge."""
    result = np.zeros_like(mask)
    if abs(dx) >= mask.shape[1]:
        return result
    if dx > 0:
        result[:, dx:] = mask[:, :-dx]
    elif dx < 0:
        result[:, :dx] = mask[:, -dx:]
    else:
        return mask.copy()
    return result


def dilate(mask):
    return np.asarray(Image.fromarray(mask).convert("L").filter(ImageFilter.MaxFilter(5))) > 0


def background(image):
    return np.asarray(image.resize((40, 25), Image.Resampling.BOX), dtype=np.int16)


def score_features(image, meta):
    rgb = np.asarray(image, dtype=np.int16)
    h, w = rgb.shape[:2]
    x0, y0, x1, y1 = rectangle(meta, "score", (h, w))
    crop = rgb[y0:y1, x0:x1]
    if min(crop.shape[:2], default=0) < 40:
        raise ValueError("Score capture rectangle is too small")
    # Max-channel intensity tolerates red, amber and mint feedback.
    # Local contrast rejects the gradually changing background and glow.
    peak = crop.max(axis=2)
    smooth = np.asarray(Image.fromarray(peak.astype("uint8")).filter(ImageFilter.GaussianBlur(4)),
                        dtype=np.int16)
    ink = (peak-smooth >= 19) & (peak >= 60)
    valid = np.ones_like(ink)
    valid[:, :16] = False  # Fixed brace/gutter at half-resolution.
    cursor = round(meta["playhead"]*w)-x0
    # The glow has a thin high-contrast edge about 17 px from the
    # cursor at 640x400. Mask the fixed overlay, not moving notation.
    radius = max(14, round(.035*w))
    valid[:, max(0,cursor-radius):max(0,cursor+radius+1)] = False
    if meta.get("count_in"):
        a,b,c,d = rectangle(meta, "count_in", (h,w))
        valid[max(0,b-y0-4):max(0,d-y0+4), max(0,a-x0-4):max(0,c-x0+4)] = False
    coverage = (ink & valid).sum(axis=1) / np.maximum(1, valid.sum(axis=1))
    rows = coverage > .38
    band = np.convolve(rows.astype(int), np.ones(5, dtype=int), mode="same") > 0
    return ink & ~band[:,None], valid, rows


def motion_shifts(before, after, width):
    old = {layer["id"]: layer for layer in before["layers"]}
    shifts = {round((old[layer["id"]]["world"]-layer["world"])*layer["density"]*width)
              for layer in after["layers"] if layer["id"] in old}
    if not shifts:
        delta = before["world"]-after["world"]
        shifts = {round(delta*layer["density"]*width) for layer in before["layers"]+after["layers"]}
    return sorted(shifts or {0})


def staff_change(ra, rb, metrics):
    near_a = np.convolve(ra.astype(int), np.ones(5,dtype=int),mode="same") > 0
    near_b = np.convolve(rb.astype(int), np.ones(5,dtype=int),mode="same") > 0
    lost_rows = int((ra & ~near_b).sum())
    new_rows = int((rb & ~near_a).sum())
    metrics.update(staff_rows_before=int(ra.sum()),staff_rows_after=int(rb.sum()),
                   lost_staff_rows=lost_rows,new_staff_rows=new_rows)
    return max(lost_rows,new_rows) >= 3 and (lost_rows > .35*ra.sum() or new_rows > .35*rb.sum())


def ink_change(a, va, b, vb, shifts, metrics, allowed=None):
    # A deliberate long hitch may leave no common written ink. The
    # stationary staff and background checks still apply.
    margin = max(abs(dx) for dx in shifts)+4
    if margin*2 >= a.shape[1]-16:
        metrics["overlap_unavailable"] = True
        return [], None
    expected = np.zeros_like(a)
    reverse = np.zeros_like(b)
    shared = vb.copy()
    backwards = va.copy()
    for dx in shifts:
        expected |= shift(a,dx)
        reverse |= shift(b,-dx)
        shared &= shift(va,dx)
        backwards &= shift(vb,-dx)
    for valid in (shared,backwards):
        valid[:, :margin] = False
        valid[:, -margin:] = False
    lost = a & backwards & ~dilate(reverse)
    added = b & shared & ~dilate(expected)
    # A witnessed new future strip can add ink, but never excuse loss
    # of previously printed ink (including during the same transition).
    added_valid = shared if allowed is None else shared & ~allowed
    added &= added_valid
    old_count = int((a & backwards).sum())
    new_count = int((b & added_valid).sum())
    metrics.update(lost_pixels=int(lost.sum()),added_pixels=int(added.sum()),
                   old_ink=old_count,new_ink=new_count)
    reasons = []
    for mask,count,label in ((lost,old_count,"visible_ink_disappeared"),
                             (added,new_count,"unexpected_interior_ink")):
        n = int(mask.sum())
        if (n >= 45 and n > .42*count) or (n >= 250 and n > .20*count):
            reasons.append(label)
    residual = added.copy()
    for dx in shifts:
        residual |= shift(lost,dx)
    return reasons, residual


def compare(before, after, previous, current):
    """Return reasons, metrics and a motion-residual mask for one frame pair."""
    metrics = {}
    reasons = []
    if before.size != after.size:
        return ["viewport_changed"], metrics, None
    change = np.abs(background(before)-background(after)).max(axis=2)
    metrics["background_changed_fraction"] = float(np.mean(change > 27))
    if metrics["background_changed_fraction"] > .36:
        reasons.append("large_background_or_screen_flash")
    if not (previous["check_score"] and current["check_score"]):
        return reasons, metrics, None
    w,h = before.size
    rect0 = rectangle(previous,"score",(h,w))
    rect1 = rectangle(current,"score",(h,w))
    if rect0 != rect1:
        if max(abs(a-b) for a,b in zip(rect0,rect1,strict=True)) > 2:
            reasons.append("score_viewport_moved_or_resized")
        return reasons, metrics, None
    score_change = np.abs(background(before.crop(rect0))-background(after.crop(rect1))).max(axis=2)
    metrics["score_background_changed_fraction"] = float(np.mean(score_change > 27))
    if metrics["score_background_changed_fraction"] > .45:
        reasons.append("large_score_flash")
    a,va,ra = score_features(before, previous)
    b,vb,rb = score_features(after, current)
    metrics["staff_present"] = bool(ra.sum() >= 3 and rb.sum() >= 3)
    shifts = motion_shifts(previous,current,w)
    metrics["expected_scroll_pixels"] = shifts
    # Explicit hand focus can reposition the staff. Do not suppress
    # background comparisons or ordinary same-hand lesson changes.
    if previous["staff_hand"] != current["staff_hand"]:
        metrics["hand_focus_changed"] = True
    elif staff_change(ra,rb,metrics):
        reasons.append("staff_disappeared_or_shifted")
    velocity = scroll_velocity(previous,current,metrics)
    if velocity:
        reasons.append(velocity)
    allowed, retired = strip_witnesses(previous,current,a.shape,rect0[0],w)
    metrics["admitted_interior_columns"] = int(allowed.any(axis=0).sum())
    if retired:
        metrics["prematurely_retired_strips"] = retired
        reasons.append("visible_strip_retired_before_exit")
    more, residual = ink_change(a,va,b,vb,shifts,metrics,allowed)
    return reasons+more, metrics, residual


def records(folder):
    """Read bounded length-prefixed PNGs paired with one metadata line each."""
    count = 0
    previous_engine_frame = None
    with (folder/"frames.bin").open("rb") as frames, (folder/"frames.jsonl").open() as metadata:
        for index,line in enumerate(metadata):
            length = frames.read(4)
            if len(length) != 4:
                raise ValueError("Truncated frame header")
            size = struct.unpack("<I",length)[0]
            if not 0 < size <= 4_000_000:
                raise ValueError("Invalid frame size")
            data = frames.read(size)
            if len(data) != size:
                raise ValueError("Truncated frame image")
            meta = json.loads(line)
            if meta["frame"] != index:
                raise ValueError("Missing or duplicate rendered frame")
            engine_frame = meta["engine_frame"]
            if previous_engine_frame is not None and engine_frame != previous_engine_frame+1:
                raise ValueError("A rendered engine frame was not captured exactly once")
            previous_engine_frame = engine_frame
            count += 1
            with Image.open(io.BytesIO(data)) as img:
                yield meta,img.convert("RGB")
        if frames.read(1):
            raise ValueError("Unmatched rendered frames")
    complete = json.loads((folder/"complete.json").read_text())
    if count != complete["frames"] or not complete["success"]:
        raise ValueError("Capture was incomplete")


def save_frame(folder, meta, image):
    image.save(folder/f"frame-{meta['frame']:06d}.png")
    (folder/f"frame-{meta['frame']:06d}.json").write_text(json.dumps(meta,indent=2))


def save_witness(folder, history, event, residual):
    folder.mkdir(parents=True, exist_ok=True)
    for meta,image in history:
        save_frame(folder,meta,image)
    if residual is not None:
        heat = np.zeros((*residual.shape,3),dtype=np.uint8)
        heat[residual] = (255,40,40)
        Image.fromarray(heat).save(folder/"motion-residual.png")
    (folder/"comparison.json").write_text(json.dumps(event,indent=2))


class Review:
    def __init__(self, output):
        self.output = output
        self.history = deque(maxlen=4)
        self.witnesses = []
        self.failures = []
        self.coverage = {"frames":0,"score_pairs":0,"motion_pairs":0,"no_overlap_pairs":0,
                         "navigation_pairs":0,"staff_pairs":0,"ink_pairs":0,
                         "phases":{},"steps":{},"max_frame_gap_ms":0.0}
        self.armed = False

    def consume(self, meta, image):
        self.coverage["frames"] += 1
        last = self.history[-1] if self.history else None
        navigating = (last is None or meta["screen"] != last[0]["screen"]
                      or (meta["piece"] != last[0]["piece"]
                          and (not self.armed or meta["step"] == "reopen")))
        if navigating:
            self.armed = False
        self.armed |= meta["ready"] and meta["screen"] == "practice"
        meta["check_score"] = self.armed and meta["screen"] == "practice"
        self.history.append((meta,image))
        for dest,until in self.witnesses:
            if meta["frame"] <= until:
                save_frame(dest,meta,image)
        if navigating:
            self.coverage["navigation_pairs"] += 1
            return
        prior,previous = last
        dt = meta["time_ms"]-prior["time_ms"]
        if not math.isfinite(dt) or dt < 0:
            raise ValueError("Nonmonotonic frame time")
        self.coverage["max_frame_gap_ms"] = max(self.coverage["max_frame_gap_ms"],dt)
        if not (prior["check_score"] and meta["check_score"]):
            return
        self.compare_pair(previous,image,prior,meta,dt)

    def compare_pair(self, previous, image, prior, meta, dt):
        self.coverage["score_pairs"] += 1
        key = f"{meta['mode']}:{meta['phase']}:{meta['step']}"
        self.coverage["phases"][key] = self.coverage["phases"].get(key,0)+1
        step = meta["step"]
        self.coverage["steps"][step] = self.coverage["steps"].get(step,0)+1
        reasons,metrics,residual = compare(previous,image,prior,meta)
        if metrics.get("overlap_unavailable"):
            self.coverage["no_overlap_pairs"] += 1
        elif any(metrics.get("expected_scroll_pixels",[])):
            self.coverage["motion_pairs"] += 1
        self.coverage["staff_pairs"] += int(metrics.get("staff_present",False))
        self.coverage["ink_pairs"] += int(min(metrics.get("old_ink",0),metrics.get("new_ink",0)) >= 45)
        if reasons:
            event = {"frame":meta["frame"],"previous":prior["frame"],"dt_ms":dt,
                     "reasons":reasons,"metrics":metrics,"phase":key}
            self.failures.append(event)
            if len(self.witnesses) < MAX_EVIDENCE:
                dest = self.output/f"failure-{meta['frame']:06d}"
                save_witness(dest,self.history,event,residual)
                self.witnesses.append((dest,meta["frame"]+3))

    def finish(self, required_steps):
        if (self.coverage["score_pairs"] < 60 or self.coverage["motion_pairs"] < 20
                or self.coverage["staff_pairs"] < 20 or self.coverage["ink_pairs"] < 20):
            self.failures.append({"reasons":["insufficient_rendered_motion_coverage"]})
        missing = sorted(set(required_steps)-self.coverage["steps"].keys())
        if missing:
            self.failures.append({"reasons":["missing_journey_steps"],"steps":missing})
        report = {"coverage":self.coverage,"failures":self.failures}
        (self.output/"report.json").write_text(json.dumps(report,indent=2))
        print(f"VISUAL_CONTINUITY frames={self.coverage['frames']} pairs={self.coverage['score_pairs']} "
              f"moving={self.coverage['motion_pairs']} failures={len(self.failures)} "
              f"report={self.output/'report.json'}")
        return not self.failures


def analyze(folder, output, required_steps=()):
    output.mkdir(parents=True, exist_ok=True)
    review = Review(output)
    try:
        for meta,image in records(folder):
            review.consume(meta,image)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        review.failures.append({"reasons":["invalid_capture"],"detail":str(exc)})
    return review.finish(required_steps)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture",type=Path)
    parser.add_argument("output",type=Path)
    parser.add_argument("--require-step",action="append",default=[])
    args = parser.parse_args()
    return 0 if analyze(args.capture,args.output,args.require_step) else 1


if __name__ == "__main__":
    raise SystemExit(main())
