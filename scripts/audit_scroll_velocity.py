"""Measure score-velocity variations using Verovio PNGs and real Godot tiles.

Run with: python scripts/audit_scroll_velocity.py
This deliberately uses the same fixture / map as the integration tests.
"""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_score_motion_render import make_render_fixture


def main() -> int:
    godot = shutil.which("godot") or shutil.which("godot4")
    if not godot:
        print("Godot 4 must be installed to audit the rendered scrolling score.", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix="piano-scroll-") as directory:
        folder = Path(directory)
        make_render_fixture(folder, bars=12)
        result = subprocess.run(
            [godot, "--headless", "--path", str(ROOT / "godot"),
             "--script", str(ROOT / "tests/godot/score_strip.gd"), "--", str(folder)],
            text=True, capture_output=True, timeout=180,
        )
        output = result.stdout + result.stderr
        for line in output.splitlines():
            if ("SCROLL_VELOCITY_AUDIT:" in line or
                    "SCROLL_JOIN_DETAIL:" in line or
                    "SCROLL_SAFE_SPLICES:" in line or
                    "SCORE_STRIP_FAILURES:" in line or "FAIL:" in line or
                    "SCRIPT ERROR:" in line):
                print(line, flush=True)
        if result.returncode:
            print(output[-5000:], file=sys.stderr)
            return result.returncode
        if "SCROLL_VELOCITY_AUDIT:" not in output:
            print("Expected real-layout velocity measurements were not produced.", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
