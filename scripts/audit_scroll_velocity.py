"""Measure real tempo-dependent scrolling in Verovio/Godot rendered pixels.

Run with: .venv/bin/python scripts/audit_scroll_velocity.py
The primary fixture has a measured maximum join-speed budget: 1.4x the
normal pixel velocity. A second, more complex two-handed fixture checks the
notehead and feedback geometry without imposing a collision-blind speed limit.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_score_motion_render import make_render_fixture

MAX_STANDARD_JOIN_RATIO = 1.25
MAX_TWO_HAND_JOIN_RATIO = 1.20
MIN_JOIN_RATIO = 0.90
VELOCITY_PATTERN = re.compile(
    r"typical=(\d+(?:\.\d+)?).*?join_min=(\d+(?:\.\d+)?).*?"
    r"join_max_ratio=(\d+(?:\.\d+)?)"
)


def make_two_hand_fixture(folder: Path, bars: int = 12) -> None:
    """Generated chords, shared attacks, eighths and a cross-bar note."""
    from piano_teacher.lesson_score import build_lesson_score
    from piano_teacher.music import Note, Phrase
    from piano_teacher.score import render_layout
    from piano_teacher.raster import rasterize_score

    beats = bars * 4
    notes = [Note(float(i), float(i + 1), 48, 0, 0, "left") for i in range(beats)]
    for bar in range(bars):
        start = bar * 4
        notes.extend([
            Note(start, start + 1, 72, 0, 0, "right"),
            Note(start, start + 1, 76, 0, 0, "right"),
            Note(start + 1, start + 1.5, 74, 0, 0, "right"),
            Note(start + 1.5, start + 2, 72, 0, 0, "right"),
            Note(start + 2, start + 3, 77, 0, 0, "right"),
        ])
        if bar % 2 == 0 and bar + 1 < bars:
            notes.append(Note(start + 3, start + 5, 79, 0, 0, "right"))
    phrase = Phrase(1, 1, bars, 0, beats, tuple(notes))
    engraved = render_layout(build_lesson_score(phrase), 1, bars,
                             "both", total_beats=beats, bpm=68)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "layout.json").write_text(json.dumps(engraved.layout))
    for page, svg in enumerate(engraved.pages):
        (folder / f"page-{page}.png").write_bytes(rasterize_score(svg))


def run_fixture(godot: str, folder: Path, label: str,
                max_join_ratio: float | None = None) -> bool:
    result = subprocess.run(
        [godot, "--headless", "--path", str(ROOT / "godot"),
         "--script", str(ROOT / "tests/godot/score_strip.gd"), "--", str(folder)],
        text=True, capture_output=True, timeout=180,
    )
    output = result.stdout + result.stderr
    print(f"SCROLL_FIXTURE: {label}", flush=True)
    for line in output.splitlines():
        if ("SCROLL_VELOCITY_AUDIT:" in line or
                "SCROLL_JOIN_DETAIL:" in line or
                "SCROLL_SAFE_SPLICES:" in line or
                "SCORE_STRIP_FAILURES:" in line or "FAIL:" in line or
                "SCRIPT ERROR:" in line):
            print(line, flush=True)
    if result.returncode or "SCORE_STRIP_FAILURES:0" not in output:
        print(output[-5000:], file=sys.stderr)
        return False
    readings = [tuple(map(float, triple))
                for triple in VELOCITY_PATTERN.findall(output)]
    if not readings:
        print(f"{label}: expected real-layout velocity measurements were not produced.",
              file=sys.stderr)
        return False
    ratio = max(maximum for _, _, maximum in readings)
    minimum = min(slowest / nominal for nominal, slowest, _ in readings)
    print(f"SCROLL_SPEED_BOUNDS: {label}: min={minimum:.3f}x, max={ratio:.3f}x",
          flush=True)
    if minimum < MIN_JOIN_RATIO:
        print(f"{label}: system joins slowed to {minimum:.3f}x, below "
              f"{MIN_JOIN_RATIO:.2f}x budget.", file=sys.stderr)
        return False
    if max_join_ratio is not None and ratio > max_join_ratio:
        print(f"{label}: system joins accelerate to {ratio:.3f}x, above "
              f"{max_join_ratio:.2f}x budget.", file=sys.stderr)
        return False
    return True


def main() -> int:
    godot = shutil.which("godot") or shutil.which("godot4")
    if not godot:
        print("Godot 4 must be installed to audit the rendered scrolling score.",
              file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix="piano-scroll-") as directory:
        folder = Path(directory)
        standard = folder / "single-hand"
        standard.mkdir()
        make_render_fixture(standard, bars=12)
        if not run_fixture(godot, standard, "single-hand rhythmic passage",
                           MAX_STANDARD_JOIN_RATIO):
            return 1
        two_hand = folder / "two-hand"
        make_two_hand_fixture(two_hand, bars=12)
        if not run_fixture(godot, two_hand, "two hands / chords / crossing ties",
                           MAX_TWO_HAND_JOIN_RATIO):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
