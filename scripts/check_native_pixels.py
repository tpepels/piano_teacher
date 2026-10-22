#!/usr/bin/env python3
"""Capture actual native Godot pixels and independently test written staff pitch.

Usage:
  xvfb-run -a -s "-screen 0 1600x1000x24" \
    python scripts/check_native_pixels.py --out /tmp/piano-native-pixel-proof

Do not confuse this limited pixel-position probe with full-sheet correctness.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess

from piano_teacher.notation.pixel_proof import verify_pixel_frames
from check_native_verovio_overlay import AuditCase, ROOT, fixture

PROBES = (
    AuditCase("independent-grand-staff-pixel-pitch",
              "tests/fixtures/native_pixel_pitch_probe.musicxml",
              1, 2, "both"),
    AuditCase("independent-grand-staff-pixel-chords",
              "tests/fixtures/native_pixel_chord_probe.musicxml",
              1, 2, "both"),
)
BEATS = tuple(float(i) for i in range(8))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    godot = shutil.which("godot") or shutil.which("godot4")
    if godot is None:
        parser.error("Actual Godot renderer is mandatory: cannot skip pixel proof")
    args.out.mkdir(parents=True, exist_ok=True)
    results = []
    for probe in PROBES:
        folder = args.out / probe.name
        folder.mkdir(parents=True, exist_ok=True)
        data, engraving = fixture(probe)
        xml = data.pop("xml")
        data["sample_beats"] = BEATS
        (folder / "input.musicxml").write_text(xml, encoding="utf-8")
        (folder / "fixture.json").write_text(json.dumps(data))
        result = subprocess.run([
            godot, "--path", str(ROOT / "godot"),
            "--rendering-method", "gl_compatibility",
            "--script", str(ROOT / "tests/godot/native_verovio_overlay.gd"),
            "--", str(folder / "fixture.json"), str(folder),
        ], capture_output=True, text=True, timeout=240)
        (folder / "godot.log").write_text(result.stdout + result.stderr)
        if result.returncode != 0 or "NATIVE_VEROVIO_OVERLAY_FAILURES:0" not in result.stdout:
            report = {"passed": False, "name": probe.name,
                      "failures": ["Actual native Godot capture failed",
                                   (result.stdout + result.stderr)[-5000:]]}
        else:
            frames = {b: folder / f"native-{b:.2f}.png" for b in BEATS}
            missing = [str(frame) for frame in frames.values() if not frame.is_file()]
            if missing:
                report = {"passed": False, "name": probe.name,
                          "failures": ["Missing required screenshots: " + str(missing)]}
            else:
                source = (ROOT / probe.filename).read_text(encoding="utf-8")
                report = verify_pixel_frames(source, frames)
                report["name"] = probe.name
        (folder / "pixel-proof-report.json").write_text(json.dumps(report, indent=2) + "\\n")
        results.append(report)
        print(f"{probe.name}: "
              f"{report.get('notes_checked_from_pixels', 0)}/"
              f"{report.get('notes_expected', '?')} source notes from Godot pixels;"
              f" pass={report['passed']}", flush=True)
        for entry in report.get("failures", []):
            print("FAIL", entry, flush=True)
    totals = {
        "passed": all(r["passed"] for r in results),
        "probes": len(results),
        "image_verified_noteheads": sum(r.get("notes_checked_from_pixels", 0)
                                        for r in results),
        "source_noteheads": sum(r.get("notes_expected", 0) for r in results),
        "results": [{"name": r["name"], "passed": r["passed"],
                     "failures": r.get("failures", [])} for r in results],
    }
    (args.out / "summary.json").write_text(json.dumps(totals, indent=2) + "\\n")
    return 0 if totals["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
