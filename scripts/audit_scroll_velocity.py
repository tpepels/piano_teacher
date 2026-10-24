"""Measure actual native source-note travel through the production Godot view.

The Verovio reference engraver remains independent of this display audit.
No raster strip, easing curve, or alternative production renderer is loaded.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MAX_STANDARD_JOIN_RATIO = 1.25
MAX_TWO_HAND_JOIN_RATIO = 1.20
MIN_JOIN_RATIO = 0.90


def _write_fixture(folder, phrase, boundaries, *, hand, meter):
    from piano_teacher.notation.lesson import build_lesson_score
    from piano_teacher.server import PracticeEngine

    folder.mkdir(parents=True, exist_ok=True)
    source = folder / "source.musicxml"
    source.write_text(build_lesson_score(phrase, boundaries=boundaries,
        time_signatures=((0, *meter),)).musicxml)
    engine = PracticeEngine(folder / "engine", enable_midi=False)
    try:
        engine.load(str(source), warmup=True)
        engine._prepare_perform(scope="whole")
        engine.plan.set_hand(hand)
        engine.plan.bpm = 68
        model = engine.semantic_score()
        layout = engine.geometry()
        (folder / "native.json").write_text(json.dumps({
            "model": model, "layout": layout, "state": engine.state()}))
    finally:
        engine.db.close()


def make_render_fixture(folder: Path, bars: int = 12) -> None:
    from piano_teacher.music import Note, Phrase

    duration = bars * 3
    notes = tuple(Note(i, i + .5, 77 - (i // 3) % 5, 0, 0, "right")
                  for i in range(duration))
    _write_fixture(folder, Phrase(1, 1, bars, 0, duration, notes),
        tuple(range(0, duration + 1, 3)), hand="right", meter=(3, 4))


def make_two_hand_fixture(folder: Path, bars: int = 12) -> None:
    from piano_teacher.music import Note, Phrase

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
    _write_fixture(folder, Phrase(1, 1, bars, 0, beats, tuple(notes)),
        tuple(range(0, beats + 1, 4)), hand="both", meter=(4, 4))


def measure_speed_bounds(payload: dict, samples: list[dict]) -> dict:
    """Validate independently clocked native head samples against source IDs."""
    expected = {event["id"]: float(event["beat"])
                for event in payload["model"]["notation_events"]
                if event["kind"] == "note"}
    if not samples or len(samples) != len(expected):
        raise ValueError("Native velocity audit did not sample every source note")
    seen = set()
    rates = []
    for sample in samples:
        identity = sample["id"]
        if identity in seen or identity not in expected:
            raise ValueError("Native velocity sample has a missing or duplicate source identity")
        seen.add(identity)
        values = [float(sample[key]) for key in ("beat", "before", "after")]
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Non-finite native velocity sample")
        if abs(values[0] - expected[identity]) > 1e-6:
            raise ValueError("Native velocity sample changed its source beat")
        # The real capture harness samples each attack at onset +/- .125.
        rate = (values[1] - values[2]) / .25
        if rate <= 0:
            raise ValueError("Native notehead stopped or moved backwards")
        rates.append(rate)
    ordered = sorted(rates)
    typical = ordered[len(ordered) // 2]
    return {"samples": len(rates), "typical": typical,
            "min_ratio": min(rates) / typical, "max_ratio": max(rates) / typical}


def run_fixture(godot: str, folder: Path, label: str,
                max_join_ratio: float | None = None) -> bool:
    result = subprocess.run(
        [godot, "--headless", "--path", str(ROOT / "godot"),
         "--script", str(ROOT / "tests/godot/score_motion.gd"), "--", str(folder)],
        text=True, capture_output=True, timeout=180)
    output = result.stdout + result.stderr
    print(f"SCROLL_FIXTURE: {label}", flush=True)
    if result.returncode or "SCORE_MOTION_FAILURES:0" not in output or "SCRIPT ERROR" in output:
        print(output[-5000:], file=sys.stderr)
        return False
    try:
        payload = json.loads((folder / "native.json").read_text())
        samples = json.loads((folder / "samples.json").read_text())
        bounds = measure_speed_bounds(payload, samples)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Invalid native motion evidence: {error}", file=sys.stderr)
        return False
    print(f"SCROLL_SPEED_BOUNDS: {label}: min={bounds['min_ratio']:.3f}x, "
          f"max={bounds['max_ratio']:.3f}x samples={bounds['samples']}", flush=True)
    if bounds["min_ratio"] < MIN_JOIN_RATIO:
        return False
    if max_join_ratio is not None and bounds["max_ratio"] > max_join_ratio:
        return False
    return True


def main() -> int:
    godot = shutil.which("godot") or shutil.which("godot4")
    if not godot:
        print("Godot 4 must be installed to audit native scrolling.", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix="piano-native-scroll-") as directory:
        folder = Path(directory)
        standard = folder / "single-hand"
        make_render_fixture(standard, bars=12)
        if not run_fixture(godot, standard, "single-hand rhythmic passage", MAX_STANDARD_JOIN_RATIO):
            return 1
        two_hand = folder / "two-hand"
        make_two_hand_fixture(two_hand, bars=12)
        if not run_fixture(godot, two_hand, "two hands / chords / crossing ties", MAX_TWO_HAND_JOIN_RATIO):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
