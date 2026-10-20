#!/usr/bin/env python3
"""Exercise real curriculum stages through authentic assets and native Godot.

Run with PIANO_TEACHER_NATIVE_NOTATION=1. Every fallback is a failure. The
default checks all learn/connect/perform variants; --measure selects learn
stages containing that source measure. Evidence stays under --output.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from piano_teacher.server import PracticeEngine


def stages(plan, measure=None):
    for index, exercise in enumerate(plan.exercises):
        if measure is not None and (exercise.kind != "learn" or not
                exercise.phrase.first_bar <= measure <= exercise.phrase.last_bar):
            continue
        plan.select(index)
        for hand in plan.hands:
            plan.set_hand(hand)
            for variant_index, variant in enumerate(plan.variants):
                yield index, hand, variant_index, variant.level


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", default="", help="MIDI filename substring")
    parser.add_argument("--measure", type=int)
    parser.add_argument("--output", type=Path, default=Path("/tmp/piano-native-notation"))
    args = parser.parse_args(argv)
    if os.environ.get("PIANO_TEACHER_NATIVE_NOTATION") != "1":
        parser.error("Set PIANO_TEACHER_NATIVE_NOTATION=1 to verify the native engine")
    godot = shutil.which("godot") or shutil.which("godot4")
    if godot is None:
        parser.error("Godot 4 is required")
    paths = [p for p in sorted((ROOT / "midi").glob("*.midi"))
             if args.only.casefold() in p.name.casefold()]
    if not paths:
        parser.error("No MIDI files match --only")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    results, failures = [], []
    for file_index, path in enumerate(paths):
        engine = PracticeEngine(output / "cache", enable_midi=False)
        try:
            engine.load(str(path))
            for index, hand, variant, level in stages(engine.plan, args.measure):
                label = f"{file_index}-{index}-{hand}-{level}"
                metadata = {"file": path.name, "exercise": index,
                            "hand": hand, "level": level}
                try:
                    engine.plan.select(index)
                    engine.plan.set_hand(hand)
                    engine.plan.variant_index = variant
                    engine.score_revision += 1
                    model = engine.semantic_score()
                    layout = engine.geometry(native_notes=True)
                    payload = output / f"{label}.json"
                    payload.write_text(json.dumps({"model": model, "layout": layout}))
                    report_path = output / f"{label}-godot.json"
                    proc = subprocess.run(
                        [godot, "--headless", "--path", str(ROOT / "godot"),
                         "--script", str(ROOT / "tests/godot/native_library.gd"),
                         "--", str(payload), str(report_path)],
                        cwd=ROOT, env={**os.environ, "PIANO_TEACHER_NATIVE_NOTATION": "1"},
                        capture_output=True, text=True, timeout=90)
                    (output / f"{label}.log").write_text(proc.stdout + proc.stderr)
                    if not report_path.exists():
                        raise RuntimeError(proc.stdout + proc.stderr)
                    report = json.loads(report_path.read_text())
                    if (proc.returncode or not report.get("native_ready") or
                            "SCRIPT ERROR" in proc.stdout + proc.stderr):
                        raise RuntimeError(str(report) + "\n" + proc.stdout + proc.stderr)
                    results.append({**metadata, **report})
                    print("NATIVE_PASS:", path.name, index, hand, level, flush=True)
                except Exception as exc:
                    failures.append({**metadata, "error": str(exc),
                                     "traceback": traceback.format_exc()})
                    print("NATIVE_FAIL:", path.name, index, hand, level, str(exc), flush=True)
                (output / "report.json").write_text(json.dumps({
                    "passed": len(results), "failed": len(failures),
                    "results": results, "failures": failures}, indent=2) + "\n")
        finally:
            engine.db.close()
    print(f"Native notation: {len(results)} passed, {len(failures)} failed; {output}")
    return int(bool(failures) or not results)


if __name__ == "__main__":
    raise SystemExit(main())
