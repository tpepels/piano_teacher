#!/usr/bin/env python3
"""Phase 6: verify real imported files through practice navigation, Verovio,
PNG rasterization, source-note mapping, and Godot's scrolling-score assembly.

All output is written outside the music folder. Each input is isolated in a
subprocess with a deadline; a corrupt or very large file cannot stop the rest.
"""
from __future__ import annotations

import argparse
import bisect
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from io import BytesIO

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from piano_teacher.library import ScoreLibrary
from piano_teacher.score import import_piece

RESULT_PREFIX = "PHASE6_RESULT:"


def sample_bars(piece) -> list[int]:
    """First, middle and last *playable* source measures, not elapsed seconds."""
    boundaries = piece.bar_boundaries
    numbers = sorted({max(1, min(len(boundaries) - 1,
        bisect.bisect_right(boundaries, note.start + 1e-7)))
        for note in piece.notes})
    if not numbers:
        raise ValueError("This file has no playable source measures")
    return list(dict.fromkeys(numbers[i] for i in (0, len(numbers)//2, len(numbers)-1)))


def check_one(path: Path, evidence: Path, *, godot: str | None) -> dict:
    from PIL import Image
    from piano_teacher.server import PracticeEngine

    started = time.monotonic()
    evidence.mkdir(parents=True, exist_ok=True)
    # Isolated data/config protects the user's progress, preferences and
    # most-recent piece; even a failed check is read-only for their library.
    with tempfile.TemporaryDirectory(prefix="piano-phase6-") as temp:
        engine = PracticeEngine(Path(temp) / "state", enable_midi=False)
        samples = []
        try:
            engine.load(str(path))
            piece = engine.plan.piece
            planned = sample_bars(piece)
            for index, bar in enumerate(planned):
                engine.control("open_at", bar=bar, mode="practice")
                state = engine.state()
                selected = int(state["selected_start_bar"])
                if selected != bar:
                    raise AssertionError(f"Selected measure {bar}, backend chose {selected}")
                if state["mode"] != "practice" or state["running"]:
                    raise AssertionError("Opening a starting measure unexpectedly began playback")
                # Real Verovio, glyph positions, timing map and exact alignment.
                layout = engine.geometry()
                engraving = engine.engraving()
                if not engraving.pages or not layout["systems"]:
                    raise AssertionError("Engraving contains no pages or staff systems")
                if not layout["notes"] or not layout["anchors"]:
                    raise AssertionError("Engraving has no timed noteheads/anchors")
                mapped = set(layout.get("attack_map", {}))
                required = {n.source_id for n in engine.plan.active_phrase.notes
                            if n.hand == engine.plan.hand or engine.plan.hand == "both"}
                if not required.issubset(mapped):
                    raise AssertionError(
                        f"{len(required-mapped)} required source attacks have no engraved glyph")
                for note in layout["notes"]:
                    if not 0 <= float(note["x"]) <= 1 or not 0 <= float(note["y"]) <= 1:
                        raise AssertionError("An engraved notehead is outside the page")
                    if not 0 <= int(note["page"]) < len(engraving.pages):
                        raise AssertionError("An engraved notehead refers to a missing page")
                files = []
                for page in range(len(engraving.pages)):
                    png = engine.engraved_png(page)
                    image = Image.open(BytesIO(png))
                    image.load()
                    if image.width < 50 or image.height < 50:
                        raise AssertionError("Rendered PNG has invalid dimensions")
                    filename = f"sample-{index+1:02d}-page-{page:02d}.png"
                    (evidence / filename).write_bytes(png)
                    files.append(filename)
                manifest = {
                    "measure": bar, "hand": engine.plan.hand,
                    "layout": layout, "pages": files,
                }
                manifest_name = f"sample-{index+1:02d}.json"
                (evidence / manifest_name).write_text(
                    json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
                samples.append({"measure": bar, "selected": selected,
                    "hand": engine.plan.hand, "pages": len(files),
                    "noteheads": len(layout["notes"]),
                    "anchors": len(layout["anchors"]),
                    "manifest": manifest_name})
            # Navigate forward and back on the real LearningPlan and keep
            # the next selected exercise inside its source measure boundaries.
            before = engine.plan.index
            engine.control("next")
            after_next = engine.plan.index
            engine.control("previous")
            after_previous = engine.plan.index
            if after_next == before and len(engine.plan.exercises) > 1:
                # The selected exercise can be the final one; previous and
                # next must then still be valid and reversible.
                engine.control("previous")
                engine.control("next")
            if not 0 <= engine.plan.index < len(engine.plan.exercises):
                raise AssertionError("Exercise navigation escaped its legal range")
            if godot:
                command = [godot, "--headless", "--path", str(ROOT / "godot"),
                           "--script", "res://diagnostic_score.gd", "--", str(evidence)]
                run = subprocess.run(command, capture_output=True, text=True,
                                     timeout=50, cwd=ROOT)
                (evidence / "godot.log").write_text(run.stdout + run.stderr)
                if run.returncode != 0 or "PHASE6_GODOT_PASS" not in run.stdout:
                    raise RuntimeError("Godot score assembly failed: " +
                                       (run.stdout + run.stderr)[-1200:])
            return {"status": "pass", "file": path.name,
                    "source_notes": len(piece.notes), "total_measures":
                    len(piece.bar_boundaries)-1,
                    "warnings": list(piece.import_warnings),
                    "samples": samples, "godot": bool(godot),
                    "duration_seconds": round(time.monotonic()-started, 2)}
        finally:
            engine.db.close()


def _worker(args) -> int:
    evidence = Path(args.evidence).resolve()
    try:
        result = check_one(Path(args.worker).resolve(), evidence, godot=args.godot)
        print(RESULT_PREFIX + json.dumps(result), flush=True)
        return 0
    except Exception as exc:
        (evidence / "failure.txt").write_text(traceback.format_exc())
        print(RESULT_PREFIX + json.dumps({"status": "fail",
            "file": Path(args.worker).name, "stage_error": str(exc),
            "error_type": type(exc).__name__}), flush=True)
        return 1


def run_library(music_dir: Path, output: Path, *, timeout: int,
                limit: int | None = None, godot: str | None = None) -> dict:
    library = ScoreLibrary(config_dir=output / ".diagnostic-config")
    # The diagnostic must never save settings or mutate the user's music.
    library._folder = music_dir.resolve()
    library.settings["music_dir"] = str(library._folder)
    listing = library.scan()
    if listing.get("error"):
        raise ValueError(listing["error"])
    entries = listing["pieces"]
    if limit is not None:
        entries = entries[:limit]
    output.mkdir(parents=True, exist_ok=True)
    results = []
    for index, entry in enumerate(entries):
        identifier = entry["id"]
        location = library.resolve(identifier)
        evidence = output / f"{index+1:04d}"
        evidence.mkdir(parents=True, exist_ok=True)
        args = [sys.executable, str(ROOT / "scripts/verify_library_pipeline.py"),
                "--worker", str(location), "--evidence", str(evidence)]
        if godot:
            args += ["--godot", godot]
        print(f"[{index+1}/{len(entries)}] {identifier}", flush=True)
        started = time.monotonic()
        try:
            run = subprocess.run(args, capture_output=True, text=True,
                                 cwd=ROOT, timeout=timeout)
            (evidence / "worker.log").write_text(run.stdout + run.stderr)
            reports = [line[len(RESULT_PREFIX):] for line in run.stdout.splitlines()
                       if line.startswith(RESULT_PREFIX)]
            item = json.loads(reports[-1]) if reports else {
                "status": "fail", "stage_error": "Worker exited without a diagnostic report"}
            if run.returncode != 0:
                item["status"] = "fail"
            item["duration_seconds"] = round(time.monotonic()-started, 2)
        except subprocess.TimeoutExpired:
            item = {"status": "timeout", "stage_error":
                    f"Exceeded {timeout}s diagnostic deadline"}
        item["id"] = identifier
        results.append(item)
        print(f"  {item['status'].upper()}: {item.get('stage_error', 'verified')}", flush=True)
        report = {"schema": "piano-library-pipeline-v1", "music_dir": str(music_dir),
                  "total": len(entries),
                  "passed": sum(x["status"] == "pass" for x in results),
                  "failed": sum(x["status"] != "pass" for x in results),
                  "completed": len(results), "godot_enabled": bool(godot),
                  "results": results}
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--music-dir", type=Path, default=ScoreLibrary()._folder)
    parser.add_argument("--output", type=Path, default=Path("/tmp/piano-library-diagnostic"))
    parser.add_argument("--timeout", type=int, default=180,
                        help="Maximum seconds per file including Godot")
    parser.add_argument("--limit", type=int, help="Check only first N library entries")
    parser.add_argument("--godot", nargs="?", const="auto", default=None,
                        help="Also verify actual Godot score assembly (auto finds executable)")
    parser.add_argument("--worker", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--evidence", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.timeout < 10 or args.limit is not None and args.limit < 1:
        parser.error("Timeout must be >=10 seconds and limit must be positive")
    godot = (shutil.which("godot") or shutil.which("godot4")) if args.godot == "auto" else args.godot
    if args.godot and not godot:
        parser.error("Godot 4 is required for --godot")
    if args.worker is not None:
        if args.evidence is None:
            parser.error("--worker requires --evidence")
        return _worker(argparse.Namespace(worker=args.worker, evidence=args.evidence, godot=godot))
    report = run_library(args.music_dir.expanduser(), args.output.expanduser().resolve(),
                         timeout=args.timeout, limit=args.limit, godot=godot)
    print(f"PHASE 6: {report['passed']} passed, {report['failed']} failed. "
          f"Report: {args.output}/report.json", flush=True)
    return int(report["failed"] > 0)


if __name__ == "__main__":
    raise SystemExit(main())
