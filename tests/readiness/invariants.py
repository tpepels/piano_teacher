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
             the rest, cues spaced at the take's own beat (5 %) and the last
             one a take beat before the first graded beat (0.1 beat);
  colour     a repeated copy (take 2+) shows feedback colour on its own heads.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

SYNC_PX = 2.0
ONSET_PX = 2.0
CUE_SPACING_FRACTION = 0.05   # cue spacing = the take's beat within 5 %
REST_MAX_BARS = 2.25          # written rest bar + count-in, automatic takes
HEAD_WIDTH_SPACES = 1.18      # Bravura noteheadBlack advance (staff spaces)
LAST_CUE_BEATS = 0.1          # last cue one take beat before the first beat
FRAME_MS = 17.0               # cues and frames are observed per display frame


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
    first_beat_notes: dict[int, int] = {}
    for row in _jsonl(run / "performer.jsonl"):
        if row.get("type") == "take":
            first_beat_notes[row["transport_id"]] = sum(
                1 for n in row.get("notes", ())
                if n["beat"] - row.get("from_beat", 0.0) < 1.0)
    dts = sorted(r["dt"] for r in frames[1:])
    frame_median_ms = dts[len(dts) // 2] if dts else None
    captures = [e for e in ev if e.get("kind") == "capture"]
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
        # Judge a take's first graded beat before any Pause in it: a Resume
        # continues from the pause point on a new strip.
        paused_t = [r["t"] for r in frames if r.get("tid") == tid and r.get("pau")]
        first_pause = min(paused_t) if paused_t else float("inf")
        playing = [r for r in rows if r.get("ph") == "playing" and r["t"] < first_pause]
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
        staff_space = None
        for r in playing[1:]:
            if "okey" in r:
                continue
            staff_space = r.get("sg", staff_space)
            for ident, dx, expected in r.get("near", []):
                if ident not in best or abs(expected) < abs(best[ident][1]):
                    best[ident] = (dx, expected, r["d"])
        # Every head is judged. The only exemption is notation, not time: in
        # a chord with a second, one head is engraved on the other side of
        # the stem, displaced by exactly one notehead width (Bravura
        # noteheadBlack, 1.18 staff spaces). Such a head passes only when its
        # column also has an on-time head and its offset is that width
        # within the same ONSET_PX.
        head_width = HEAD_WIDTH_SPACES * staff_space if staff_space else None
        columns: dict = {}
        for dx, exp, d in best.values():
            if abs(exp) < 0.12 * d:
                columns.setdefault(round(exp, 1), []).append(dx - exp)
        offsets, displaced = [], 0
        for heads in columns.values():
            on_time = min(abs(v) for v in heads) <= ONSET_PX
            for v in heads:
                if (abs(v) > ONSET_PX and on_time and head_width is not None
                        and abs(abs(v) - head_width) <= ONSET_PX):
                    displaced += 1
                    continue
                offsets.append(v)
        take["displaced_second_heads"] = displaced
        take["onset_px_n"] = len(offsets)
        take["onset_px_max"] = max((abs(v) for v in offsets), default=None)
        take["onset_px_median"] = statistics.median(offsets) if offsets else None
        # Count-in: syllables in the rest before this take's first graded beat,
        # at this take's own tempo. The first beat's time is interpolated
        # from the transport beat of the first phase-locked frame.
        # Robust to one stalled frame: the median of the first three
        # phase-locked frames (close to beat 0, so a tempo map's rate
        # differing from the nominal BPM hardly matters).
        first_beat_t = statistics.median(r["t"] - r["tb"] * beat_ms for r in graded[:3])
        previous_end = 0
        if index > 0:
            before = [r for r in frames if r.get("tid") == tids[index - 1]
                      and r.get("ph") == "playing" and r["t"] < first["t"]]
            previous_end = before[-1]["t"] if before else 0
        window_start = first_beat_t - (bar + 0.5) * beat_ms
        rest = [v for v in voices if previous_end < v["t"] <= first["t"]]
        in_bar = [v for v in rest if v["t"] >= window_start]
        cue_t = [v["t"] for v in in_bar]
        spacing = [b - a for a, b in zip(cue_t, cue_t[1:])]
        # Owner M3: compound meters (6/8, 9/8, 12/8) count the dotted-quarter
        # pulse; every other meter counts its beats.
        meter = meta.get("cim") or [4, 4]
        pulse = 1.5 if (len(meter) == 2 and int(meter[1]) == 8
                        and int(meter[0]) in (6, 9, 12)) else 1.0
        take["count_in_pulse_beats"] = pulse
        allowed = max(CUE_SPACING_FRACTION * beat_ms * pulse, FRAME_MS)
        take["count_in_numbers"] = [v["number"] for v in in_bar]
        take["early_cues"] = [v["number"] for v in rest if v["t"] < window_start]
        take["cue_spacing_beats"] = [round(d / beat_ms, 3) for d in spacing]
        take["last_cue_to_first_beat_beats"] = (
            round((first_beat_t - cue_t[-1]) / beat_ms, 3) if cue_t else None)
        expected_cues = list(range(1, int(round(bar / pulse)) + 1)) if bar > 0 else []
        rest_paused = any(e.get("kind") == "press" and "(rest)" in str(e.get("button", ""))
                          and previous_end < e["t"] < first["t"] for e in ev)
        take["rest_paused"] = rest_paused
        last_ok = bool(cue_t) and abs(take["last_cue_to_first_beat_beats"] - pulse) \
            <= LAST_CUE_BEATS + FRAME_MS / beat_ms
        if rest_paused:
            # Pause inside the count-in bar (owner rule 8): Resume continues
            # with the rest of that bar, each syllable at most once; a cue
            # due while paused or observed late is not spoken. What is spoken
            # is non-empty, rises, has nothing before the bar and ends on the
            # bar's last syllable one pulse before beat 0.
            heard = take["count_in_numbers"]
            take["count_in_ok"] = (bool(heard) and heard == sorted(set(heard))
                                   and not take["early_cues"] and last_ok)
        else:
            # Every interval, the first Play's first one included: Godot
            # speaks a count-in it reserved from its own deadline (M4).
            take["count_in_ok"] = (take["count_in_numbers"] == expected_cues
                                   and not take["early_cues"] and bool(cue_t)
                                   and all(abs(d - pulse * beat_ms) <= allowed
                                           for d in spacing)
                                   and last_ok)
        # Owner P5: rest + count-in from the previous take's end to this
        # take's first graded beat, for automatic continuations.
        take["rest_seconds"] = take["rest_bars"] = None
        take["automatic"] = False
        if index > 0 and "first_beat_t" in takes[index - 1]:
            prev = takes[index - 1]
            prev_meta = starts[tids[index - 1]]
            prev_end = prev["first_beat_t_exact"] + float(prev_meta.get("len") or 0.0) * \
                60000.0 / float(prev_meta.get("bpm") or bpm)
            # A Pause inside the previous take moves its end: its last
            # playing frame is the real end (round 4: rests of re-engraved
            # takes after a paused take were overstated by the pause).
            prev_end = max(prev_end, previous_end)
            presses = [e for e in ev if e.get("kind") == "press"
                       and prev["first_beat_t_exact"] - 500 < e["t"] < first_beat_t]
            take["automatic"] = not presses
            retries = [e for e in presses if str(e.get("button", "")).startswith("Retry")]
            take["since_retry_seconds"] = (round((first_beat_t - retries[-1]["t"]) / 1000.0, 2)
                                           if retries else None)
            take["rest_seconds"] = round((first_beat_t - prev_end) / 1000.0, 2)
            take["rest_bars"] = round((first_beat_t - prev_end) / (bar * beat_ms), 2) if bar else None
        take["first_beat_t_exact"] = first_beat_t
        # A take with notes in its first beat must have measured onsets.
        take["notes_in_first_beat"] = first_beat_notes.get(tid, 0)
        take["onsets_measured"] = take["onset_px_n"] > 0 or not take["notes_in_first_beat"]
        take["ok"] = bool(take["bound"] and take["visible_heads"] > 0
                          and take["sync_px_max"] is not None
                          and take["sync_px_max"] <= SYNC_PX
                          and take["onsets_measured"]
                          and (take["onset_px_max"] is None or take["onset_px_max"] <= ONSET_PX)
                          and take["count_in_ok"])
        # Owner P5 / round 4: EVERY automatic continuation (announced
        # repeats, re-engraved stages, remediations, handoffs) has its
        # written rest bar plus count-in within REST_MAX_BARS. A Pause in
        # the rest lengthens it by the user's own pause.
        take["rest_ok"] = (not take["automatic"] or take["rest_paused"]
                           or take["rest_bars"] is None
                           or take["rest_bars"] <= REST_MAX_BARS)
        take["ok"] = take["ok"] and take["rest_ok"]
        takes.append(take)
    colour = _repeat_colour(run)
    starts_t = sorted((starts[t]["t"], t) for t in tids)
    for take in takes:
        take["coloured_heads"] = colour.get(take["tid"], 0)
        # Colour is judged only where a capture shows this take's heads at
        # least a beat after its first graded beat (left of the playhead).
        if "first_beat_t" in take:
            end = next((t for t, tid in starts_t if tid > take["tid"]), float("inf"))
            take["captures_after_first_beat"] = sum(
                1 for c in captures
                if take["first_beat_t"] < c["t"] < end and float(c.get("tb", -1)) >= 1.0)
    return {"run": str(run), "takes": takes, "frame_median_ms": frame_median_ms,
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
