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
from scripts.check_native_verovio_overlay import AuditCase, ROOT, fixture

PROBE = AuditCase(
    "independent-grand-staff-pixel-pitch",
    "tests/fixtures/native_pixel_pitch_probe.musicxml",
    1, 2, "both",
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
    data, engraving = fixture(PROBE)
    xml = data.pop("xml")
    data["sample_beats"] = BEATS
    (args.out / "input.musicxml").write_text(xml, encoding="utf-8")
    (args.out / "fixture.json").write_text(json.dumps(data))
    result = subprocess.run([
        godot, "--path", str(ROOT / "godot"),
        "--rendering-method", "gl_compatibility",
        "--script", str(ROOT / "tests/godot/native_verovio_overlay.gd"),
        "--", str(args.out / "fixture.json"), str(args.out),
    ], capture_output=True, text=True, timeout=240)
    (args.out / "godot.log").write_text(result.stdout + result.stderr)
    if result.returncode != 0 or "NATIVE_VEROVIO_OVERLAY_FAILURES:0" not in result.stdout:
        report = {"passed": False,
                  "failures": ["Actual native Godot capture failed", (result.stdout + result.stderr)[-5000:]]}
        (args.out / "pixel-proof-report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
        return 1
    frames = {b: args.out / f"native-{b:.2f}.png" for b in BEATS}
    for frame in frames.values():
        if not frame.is_file():
            parser.error(f"Missing required screenshot: {frame}")
    source = (ROOT / PROBE.filename).read_text(encoding="utf-8")
    report = verify_pixel_frames(source, frames)
    (args.out / "pixel-proof-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Independent screenshot pitch proof: "
          f"{report['notes_checked_from_pixels']}/{report['notes_expected']} "
          f"notes in {report['frames']} actual Godot frames")
    for entry in report["failures"]:
        print("FAIL", entry)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
