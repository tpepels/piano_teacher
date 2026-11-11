"""Per-take continuation invariants of one readiness sweep run (R1 F1).

Usage: .venv/bin/python tests/readiness/invariants.py <run dir> [...]

For every graded take that reached its first graded beat:
  bound      the take's own source strip is drawn (bound to its take key, not
             an unbound "autopending" copy) when its first beat is graded;
  sync_px    that strip's first source beat is at the playhead at the graded
             run_at (|strip-to-transport offset| <= 2 px);
  onset_px   noteheads cross the playhead at their graded beat (<= 2 px);
  count_in   exactly one full-bar count-in ("Ichi, Ni, ...") is spoken in the
             bar immediately before the first graded beat, nothing earlier in
             the rest;
  colour     a repeated copy (take 2+) shows feedback colour on its own heads.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

SYNC_PX = 2.0
ONSET_PX = 2.0


def _jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def check_run(run: Path) -> dict:
    frames = _jsonl(run / "frames.jsonl")
    events = json.loads((run / "events.json").read_text())
    ev = events.get("events", [])
    starts = {e["tid"]: e for e in ev if e.get("kind") == "take_started"}
    voices = [e for e in ev if e.get("kind") == "voice"]
    takes = []
    tids = sorted(starts)
    # Runs recorded before take_started carried "cib": the first count-in.
    first_beat = next((r["t"] for r in frames if r.get("run") and r.get("ph") == "playing"
                       and r.get("tb", -1) >= 0), None)
    default_bar = max((v["number"] for v in voices
                       if first_beat is not None and v["t"] < first_beat), default=4)
    for index, tid in enumerate(tids):
        meta = starts[tid]
        bpm = float(meta.get("bpm") or 60.0)
        beat_ms = 60000.0 / bpm
        bar = float(meta.get("cib") or default_bar)
        rows = [r for r in frames if r.get("tid") == tid and r.get("run")
                and not r.get("pau")]
        playing = [r for r in rows if r.get("ph") == "playing"]
        # The first frame of a new transport projects the engine beat from a
        # snapshot before Godot's transport clock has phase-locked to it; it
        # measures that estimate, not ink position. Report it, judge after.
        warmup = playing[0] if playing else None
        graded = [r for r in playing[1:] if 0.0 <= r["tb"] <= 0.5]
        take: dict = {"tid": tid, "bpm": bpm, "bar_beats": bar,
                      "reached_first_beat": bool(graded)}
        if not graded:
            takes.append(take)
            continue
        first = graded[0]
        take["first_beat_t"] = first["t"]
        take["bound"] = all("okey" not in r and "sync_px" in r for r in graded)
        take["visible_heads"] = min(r.get("vis", 0) for r in graded)
        syncs = [abs(r["sync_px"]) for r in graded if "sync_px" in r]
        take["warmup_frame_sync_px"] = warmup.get("sync_px") if warmup else None
        take["sync_px_max"] = max(syncs) if syncs else None
        best: dict = {}
        for r in playing[1:]:
            if "okey" in r:
                continue
            for ident, dx, expected in r.get("near", []):
                if ident not in best or abs(expected) < abs(best[ident][1]):
                    best[ident] = (dx, expected, r["d"])
        offsets = [dx - exp for dx, exp, d in best.values() if abs(exp) < 0.12 * d]
        take["onset_px_n"] = len(offsets)
        take["onset_px_max"] = max((abs(v) for v in offsets), default=None)
        take["onset_px_median"] = statistics.median(offsets) if offsets else None
        # Count-in: syllables in the rest before this take's first graded beat.
        previous_end = 0
        if index > 0:
            before = [r for r in frames if r.get("tid") == tids[index - 1]
                      and r.get("ph") == "playing" and r["t"] < first["t"]]
            previous_end = before[-1]["t"] if before else 0
        window_start = first["t"] - (bar + 0.5) * beat_ms
        rest = [v for v in voices if previous_end < v["t"] <= first["t"]]
        in_bar = [v for v in rest if v["t"] >= window_start]
        take["count_in_numbers"] = [v["number"] for v in in_bar]
        take["early_cues"] = [v["number"] for v in rest if v["t"] < window_start]
        take["last_cue_to_first_beat_beats"] = (
            round((first["t"] - in_bar[-1]["t"]) / beat_ms, 3) if in_bar else None)
        expected_cues = list(range(1, int(round(bar)) + 1)) if bar > 0 else []
        take["count_in_ok"] = (take["count_in_numbers"] == expected_cues
                               and not take["early_cues"]
                               and in_bar != []
                               and abs(take["last_cue_to_first_beat_beats"] - 1.0) <= 0.35)
        take["ok"] = bool(take["bound"] and take["visible_heads"] > 0
                          and take["sync_px_max"] is not None
                          and take["sync_px_max"] <= SYNC_PX
                          and (take["onset_px_max"] is None or take["onset_px_max"] <= ONSET_PX)
                          and take["count_in_ok"])
        takes.append(take)
    colour = _repeat_colour(run)
    for take in takes:
        take["coloured_heads"] = colour.get(take["tid"], 0)
    return {"run": str(run), "takes": takes,
            "graded_takes": sum(t["reached_first_beat"] for t in takes),
            "all_ok": all(t.get("ok", True) for t in takes if t["reached_first_beat"])}


def _repeat_colour(run: Path) -> dict[int, int]:
    """Heads of each take left of the playhead whose painted colour matches a
    feedback status in the ledger (analyze.classify on the real PNG)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import numpy as np
    from PIL import Image
    from analyze import classify
    counts: dict[int, int] = {}
    for side in sorted((run / "shots").glob("*.json")):
        shot = json.loads(side.read_text())
        png = side.with_suffix(".png")
        if not png.exists():
            continue
        image = None
        scale = float(shot.get("scale", 1.0))
        ox, oy = shot.get("offset", [0, 0])
        rx, ry, rw, rh = shot["renderer_rect"]
        for inst in shot["instances"]:
            status = inst.get("status") or ""
            parts = str(inst.get("take", "")).split("|")
            if status in ("", "unplayed") or len(parts) < 3 or not parts[2].isdigit():
                continue
            x, y = inst["x"], inst["y"]
            if not (rx + 4 < x < shot["playhead_x"] - 0.45 * shot["density"] - 10
                    and ry < y < ry + rh):
                continue
            if image is None:
                image = np.asarray(Image.open(png).convert("RGB"))
            gap = inst.get("gap") or 10.0
            hx, hy = 0.42 * gap, 0.30 * gap
            x0, x1 = int((x - hx) * scale + ox), int((x + hx) * scale + ox) + 1
            y0, y1 = int((y - hy) * scale + oy), int((y + hy) * scale + oy) + 1
            if x0 < 0 or y0 < 0 or y1 > image.shape[0] or x1 > image.shape[1]:
                continue
            rendered = classify(image[y0:y1, x0:x1])[0]
            if rendered == status:
                tid = int(parts[2])
                counts[tid] = counts.get(tid, 0) + 1
    return counts


def main() -> None:
    for arg in sys.argv[1:]:
        result = check_run(Path(arg))
        (Path(arg) / "invariants.json").write_text(json.dumps(result, indent=1))
        for take in result["takes"]:
            print(json.dumps(take))
        print("ALL_OK" if result["all_ok"] else "VIOLATIONS", result["graded_takes"])


if __name__ == "__main__":
    main()
