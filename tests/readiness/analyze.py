"""Analyse one R1 readiness sweep run (tests/readiness/run_sweep.sh output).

Usage: .venv/bin/python tests/readiness/analyze.py <run dir> [...]
Writes <run dir>/analysis.json and prints a short summary.

Colour check per captured frame and per drawn notehead instance:
  rendered  = nearest palette colour of the head's own pixels in the PNG
  ledger    = the Godot note-status ledger's status for (take, note)
  python    = display status of Python's latest assessment for that note
  plan      = what the simulated pianist did to that note
Heads near the (mint) playhead glow are excluded from the pixel check.
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

INK_SOURCE = Path(__file__).resolve().parents[2] / "godot" / "note_status_ink.gd"


def ink_palette(source: Path = INK_SOURCE) -> dict[str, tuple[int, int, int]]:
    """Status colours read from the painter's own constants (NoteStatusInk
    COLORS, e.g. EARLY_ONSET), so a palette change cannot desynchronise the
    pixel classifier."""
    import re
    text = source.read_text(encoding="utf-8")
    named = {m.group(1): m.group(2) for m in re.finditer(
        r'^const (\w+)\s*:?=\s*Color\("#?([0-9A-Fa-f]{6})"\)', text, re.M)}
    block = text[text.index("const COLORS"):]
    block = block[:block.index("}")]
    palette = {}
    for status, value in re.findall(r'"(\w+)":\s*([^,\n]+)', block):
        literal = re.search(r'Color\("#?([0-9A-Fa-f]{6})"\)', value)
        hexcode = literal.group(1) if literal else named.get(value.strip())
        if hexcode is None:
            raise ValueError(f"Cannot resolve ink colour {status}: {value}")
        palette[status] = tuple(int(hexcode[i:i + 2], 16) for i in (0, 2, 4))
    return palette


PALETTE = {"unplayed": (0xEE, 0xF5, 0xF1), **ink_palette()}
MUTED = (0x81, 0x91, 0x8B)
PLAN_TO_STATUS = {"hit": "hit", "late": "late", "early_onset": "early_onset",
                  "early_release": "early_release", "missed": "missed", "wrong": "missed"}


def display_status(dims: dict) -> str:
    pitch, onset, release = (str(dims.get(k) or "") for k in ("pitch", "onset", "release"))
    if pitch in ("missed", "wrong"):
        return "missed"
    if onset == "late":
        return "late"
    if onset == "early":
        return "early_onset"
    if release == "short":
        return "early_release"
    if release in ("long", "unreleased"):
        return "late"
    if pitch == "correct" or onset == "on_time" or release == "on_time":
        return "hit"
    return "unplayed"


def jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def pct(values, q):
    if not values:
        return None
    values = sorted(values)
    return values[min(len(values) - 1, int(round(q * (len(values) - 1))))]


def classify(pixels: np.ndarray) -> tuple[str, list[int], float]:
    """Status colour of one head from its most saturated pixels.

    White ink, ledger lines and stems are unsaturated, so a tinted head
    (filled or hollow outline) is found by chroma, not brightness.
    """
    flat = pixels.reshape(-1, 3).astype(float)
    chroma = flat.max(axis=1) - flat.min(axis=1)
    top = np.percentile(chroma, 85)
    if top < 70:
        luminance = flat.sum(axis=1)
        keep = flat[luminance >= np.percentile(luminance, 66)]
        mean = keep.mean(axis=0)
        return ("unplayed" if mean.sum() > 450 else "muted"), [int(v) for v in mean], float(top)
    keep = flat[chroma >= top * 0.9]
    mean = keep.mean(axis=0)
    best, distance = "", 1e9
    for name, rgb in PALETTE.items():
        if name == "unplayed":
            continue
        d = float(np.linalg.norm(mean - np.array(rgb)))
        if d < distance:
            best, distance = name, d
    return best, [int(v) for v in mean], distance


def analyse(run: Path) -> dict:
    events = json.loads((run / "events.json").read_text()) if (run / "events.json").exists() else {}
    frames = jsonl(run / "frames.jsonl")
    perf = jsonl(run / "performer.jsonl")
    feedback = jsonl(run / "feedback.jsonl")
    result: dict = {"run": str(run), "finish": events.get("reason")}
    ev = events.get("events", [])
    # ---- timings ------------------------------------------------------
    t_ready, t_play, t_ink = (events.get(k, -1) for k in ("t_ready_ms", "t_play_ms", "t_first_ink_ms"))
    first_at_playhead = next((e["t"] for e in ev if e.get("kind") == "capture"
                              and "first_note_at_playhead" in e.get("file", "")), None)
    result["timings"] = {"launch_to_ready_ms": t_ready, "play_to_first_ink_ms":
                         (t_ink - t_play) if t_ink >= 0 and t_play >= 0 else None,
                         "play_to_first_note_at_playhead_ms":
                         (first_at_playhead - t_play) if first_at_playhead and t_play >= 0 else None}
    ready = next((e for e in ev if e.get("kind") == "ready"), {})
    result["ready"] = {k: ready.get(k) for k in ("notes", "steps", "bpm", "strategy")}
    # ---- frame times ----------------------------------------------------
    moving = []
    for i, row in enumerate(frames):
        if i == 0 or row.get("cap") or frames[i - 1].get("cap"):
            continue
        if row.get("foc") is False or (i and frames[i - 1].get("foc") is False):
            continue  # unfocused window: the compositor throttles frames
        if row.get("run") and not row.get("pau") and row.get("ph") in ("count_in", "playing"):
            moving.append(row)
    dts = [r["dt"] for r in moving]
    worst = sorted(moving, key=lambda r: -r["dt"])[:8]
    result["frames"] = {
        "moving_frames": len(dts), "median_ms": statistics.median(dts) if dts else None,
        "p95_ms": pct(dts, .95), "p99_ms": pct(dts, .99), "max_ms": max(dts) if dts else None,
        "over_25ms": sum(d > 25 for d in dts), "over_33ms": sum(d > 33.4 for d in dts),
        "over_50ms": sum(d > 50 for d in dts), "over_100ms": sum(d > 100 for d in dts),
        "worst": [{"t": r["t"], "dt": r["dt"], "ph": r["ph"], "tb": r["tb"], "tid": r["tid"]}
                  for r in worst]}
    all_dts = [r["dt"] for i, r in enumerate(frames) if i and not frames[i-1].get("cap") and not r.get("cap")]
    result["frames"]["all_max_ms"] = max(all_dts) if all_dts else None
    result["frames"]["unfocused_frames"] = sum(1 for r in frames if r.get("foc") is False)
    # ---- motion: sync and onset offsets ----------------------------------
    sync = [r["sync_px"] for r in moving if r.get("ph") == "playing" and "sync_px" in r]
    result["sync_px"] = {"n": len(sync), "median": statistics.median(sync) if sync else None,
                         "p05": pct(sync, .05), "p95": pct(sync, .95),
                         "max_abs": max((abs(v) for v in sync), default=None)}
    best: dict = {}
    for r in moving:
        if r.get("ph") != "playing":
            continue
        for ident, dx, expected in r.get("near", []):
            key = (r["tid"], ident)
            if key not in best or abs(expected) < abs(best[key][1]):
                best[key] = (dx, expected, r["t"], r["d"])
    offsets = [dx - exp for (dx, exp, _, d) in best.values() if abs(exp) < 0.12 * d]
    result["onset_offset_px"] = {"n": len(offsets),
                                 "median": statistics.median(offsets) if offsets else None,
                                 "p05": pct(offsets, .05), "p95": pct(offsets, .95),
                                 "max_abs": max((abs(v) for v in offsets), default=None)}
    # ---- per take: is the graded passage on screen, and where? ------------
    per_take = []
    for tid in sorted({r["tid"] for r in frames if r.get("tid", -1) > 0}):
        playing = [r for r in frames if r["tid"] == tid and r.get("ph") == "playing"
                   and r.get("run") and not r.get("pau")]
        if not playing:
            continue
        early = playing[: max(1, len(playing) // 3)]
        syncs = [r["sync_px"] for r in playing if "sync_px" in r]
        keys = defaultdict(int)
        for r in playing:
            keys[r.get("okey", "bound") if "sync_px" in r else "none"] += 1
        med = statistics.median(syncs) if syncs else None
        density = statistics.median([r["d"] for r in playing])
        verdict = ("no_ink" if sum(r["vis"] > 0 for r in early) < 0.2 * len(early) else
                   "offset" if med is not None and abs(med) > 5 else
                   "ok" if med is not None else "unmeasured")
        per_take.append({"tid": tid, "playing_frames": len(playing),
                         "early_visible_fraction": round(sum(r["vis"] > 0 for r in early) / len(early), 2),
                         "median_sync_px": med, "sync_beats": round(med / density, 3) if med else None,
                         "strip_key": dict(keys), "verdict": verdict,
                         "bpm_density": density})
    result["per_take"] = per_take
    # ---- appearance -----------------------------------------------------
    empty = [r for r in moving if r.get("ph") == "playing" and r.get("vis", 0) == 0]
    not_ready = [r for r in moving if not r.get("rr")]
    inside = [e for e in ev if e.get("kind") == "ink_appeared_inside"]
    by_take: dict = defaultdict(list)
    for e in inside:
        by_take[e["take"]].append(e)
    pop = []
    for take, items in by_take.items():
        xs = [i["x"] for i in items]
        pop.append({"take": take.split("|")[2] if "|" in take else take, "count": len(items),
                    "t": min(i["t"] for i in items), "since_play_ms": min(i["since_play_ms"] for i in items),
                    "min_x": min(xs), "w": items[0]["w"]})
    result["appearance"] = {"empty_strip_moving_frames": len(empty),
                            "empty_strip_times": [r["t"] for r in empty[:10]],
                            "retained_not_ready_frames": len(not_ready),
                            "ink_appeared_inside_viewport": pop}
    # ---- count-in -------------------------------------------------------
    voices = [e for e in ev if e.get("kind") == "voice"]
    groups, current = [], []
    for v in voices:
        if current and (v["t"] - current[-1]["t"] > 4000 or v["number"] <= current[-1]["number"]):
            groups.append(current)
            current = []
        current.append(v)
    if current:
        groups.append(current)
    playing_starts = [e for e in ev if e.get("kind") == "engine_phase" and e.get("to") == "playing"]
    bpm_now = float(ready.get("bpm") or 60)
    result["count_in"] = []
    for g in groups:
        nxt = next((e for e in playing_starts if e["t"] > g[-1]["t"] - 200), None)
        tid_bpm = next((float(m.get("bpm") or bpm_now) for k, m in events.get("take_meta", {}).items()
                        if nxt and int(k) == nxt["tid"]), bpm_now)
        result["count_in"].append({
            "tid": g[0]["tid"], "t": g[0]["t"], "numbers": [v["number"] for v in g],
            "first_tb": round(g[0]["tb"], 3), "last_tb": round(g[-1]["tb"], 3),
            "last_cue_to_graded_playing_ms": (nxt["t"] - g[-1]["t"]) if nxt else None,
            "one_beat_ms": round(60000 / tid_bpm)})
    # ---- takes / plan / grading -----------------------------------------
    takes = {p["transport_id"]: p for p in perf if p.get("type") == "take"}
    latest: dict = {}
    for f in feedback:
        if f.get("kind") == "assessment":
            latest[(f["transport_id"], f["note_id"])] = f
    by_source: dict = {}
    for f in feedback:
        if f.get("kind") == "assessment":
            by_source[(f["transport_id"], f.get("source_id"))] = f
    grading = []
    for tid, take in takes.items():
        mism = []
        for note in take["notes"]:
            f = by_source.get((tid, note["source_id"]))
            got = display_status(f["dimensions"]) if f else "none"
            want = PLAN_TO_STATUS[note["outcome"]]
            if got != want:
                mism.append({"source_id": note["source_id"], "plan": note["outcome"], "python": got,
                             "dims": f["dimensions"] if f else None, "beat": note["beat"]})
        grading.append({"tid": tid, "plan": take["plan"], "notes": len(take["notes"]),
                        "planned": {o: sum(n["outcome"] == o for n in take["notes"])
                                    for o in PLAN_TO_STATUS},
                        "bpm": take["bpm"], "hand": take["hand"], "from_beat": take["from_beat"],
                        "python_vs_plan_mismatches": mism})
    result["takes"] = grading
    # ---- colour in captured frames --------------------------------------
    plan_by = {(tid, n["source_id"]): n["outcome"] for tid, t in takes.items() for n in t["notes"]}
    colour_rows = []
    history: dict = defaultdict(list)
    for f in feedback:
        if f.get("kind") == "assessment":
            history[(f["transport_id"], f["note_id"])].append((f["t"], display_status(f["dimensions"])))
    clock_offset = None
    first = next((e for e in ev if e.get("kind") == "take_started"), None)
    if first is not None and first["tid"] in takes:
        clock_offset = takes[first["tid"]]["now"] - first["t"] / 1000.0
    for side in sorted((run / "shots").glob("*.json")):
        shot = json.loads(side.read_text())
        png = side.with_suffix(".png")
        if not png.exists():
            continue
        image = np.asarray(Image.open(png).convert("RGB"))
        scale = float(shot.get("scale", 1.0))
        ox, oy = shot.get("offset", [0, 0])
        rx, ry, rw, rh = shot["renderer_rect"]
        playhead = shot["playhead_x"]
        for inst in shot["instances"]:
            x, y = inst["x"], inst["y"]
            if not (rx + 4 < x < rx + rw - 4 and ry < y < ry + rh):
                continue
            if inst["clip"][0] > x or inst["clip"][1] < x:
                continue
            near_playhead = abs(x - playhead) < 0.45 * shot["density"] + 10
            gap = inst["gap"] or 10.0
            hx, hy = 0.42 * gap, 0.30 * gap
            x0, x1 = int((x - hx) * scale + ox), int(math.ceil((x + hx) * scale + ox))
            y0, y1 = int((y - hy) * scale + oy), int(math.ceil((y + hy) * scale + oy))
            if x1 <= x0 or y1 <= y0 or y0 < 0 or x0 < 0 or y1 > image.shape[0] or x1 > image.shape[1]:
                continue
            rendered, rgb, dist = classify(image[y0:y1, x0:x1])
            parts = inst["take"].split("|")
            tid = int(parts[2]) if len(parts) > 2 and parts[2].lstrip("-").isdigit() else None
            f = latest.get((tid, inst["id"]))
            py = display_status(f["dimensions"]) if f else "unplayed"
            # Python's status(es) when the frame was drawn (clock offset from
            # the first take start, 300 ms delivery allowance).
            at_capture = {"unplayed"}
            if clock_offset is not None:
                t_py = shot["t"] / 1000.0 + clock_offset
                hist = history.get((tid, inst["id"]), [])
                before = [h for h in hist if h[0] <= t_py]
                at_capture = {before[-1][1] if before else "unplayed"}
                at_capture |= {h[1] for h in hist if t_py - 0.3 <= h[0] <= t_py}
            colour_rows.append({
                "shot": png.name, "id": inst["id"], "src": inst["src"], "tid": tid,
                "x": round(x, 1), "y": round(y, 1), "near_playhead": near_playhead,
                "right_of_playhead": x > playhead, "rendered": rendered, "rgb": rgb,
                "dist": round(dist, 1), "ledger": inst["status"] or "unplayed",
                "python_final": py, "python_at_capture": sorted(at_capture),
                "plan": plan_by.get((tid, inst["src"]))})
    checked = [r for r in colour_rows if not r["near_playhead"]]
    def bad(r):
        want = r["ledger"]
        got = r["rendered"]
        if got == "muted":
            got = "unplayed"
        return got != want
    paint_mismatch = [r for r in checked if bad(r)]
    ledger_vs_python = [r for r in checked if not r["right_of_playhead"] and r["plan"] is not None
                        and r["ledger"] not in r["python_at_capture"]
                        and r["ledger"] != r["python_final"]]
    result["colour"] = {"heads_checked": len(checked),
                        "coloured_heads": sum(r["ledger"] != "unplayed" for r in checked),
                        "paint_vs_ledger_mismatches": len(paint_mismatch),
                        "paint_vs_ledger_examples": paint_mismatch[:25],
                        "ledger_vs_python_at_capture": len(ledger_vs_python),
                        "ledger_vs_python_examples": ledger_vs_python[:25],
                        "by_status": {s: sum(r["ledger"] == s for r in checked) for s in PALETTE}}
    (run / "colour_rows.json").write_text(json.dumps(colour_rows, indent=1))
    return result


def main() -> None:
    for arg in sys.argv[1:]:
        run = Path(arg)
        result = analyse(run)
        (run / "analysis.json").write_text(json.dumps(result, indent=1))
        print(json.dumps({k: result[k] for k in ("finish", "timings", "ready", "count_in")}, indent=None))
        fr = result["frames"]
        print("frames", {k: fr[k] for k in fr if k != "worst"})
        print("sync", result["sync_px"], "onset", result["onset_offset_px"])
        print("appearance", result["appearance"])
        for t in result["per_take"]:
            print("motion take", t["tid"], t["verdict"], "visible", t["early_visible_fraction"],
                  "sync_px", t["median_sync_px"], "beats", t["sync_beats"], t["strip_key"])
        for t in result["takes"]:
            print("take", t["tid"], t["plan"], t["notes"], t["planned"],
                  "mismatch", len(t["python_vs_plan_mismatches"]))
        c = result["colour"]
        print("colour", {k: c[k] for k in c if not k.endswith("examples")})


if __name__ == "__main__":
    main()
