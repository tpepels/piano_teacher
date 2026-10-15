"""Real Godot score projection regression, including transparent PNG margins."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def make_render_fixture(folder, bars=2):
    from piano_teacher.music import Note, Phrase
    from piano_teacher.exercise_generator import generate_variants
    from piano_teacher.lesson_score import build_lesson_score
    from piano_teacher.score import render_layout
    from piano_teacher.raster import rasterize_score
    from piano_teacher.notation_symbols import preparation_symbols

    duration = bars * 3
    notes = tuple(Note(i, i + .5, 77 - (i // 3) % 5, 0, 0, "right")
                  for i in range(duration))
    phrase = Phrase(1, 1, bars, 0, duration, notes)
    variant = generate_variants(phrase, "right")[-1]
    score = build_lesson_score(variant.phrase, boundaries=tuple(range(0, duration + 1, 3)))
    # Render at an actual lesson tempo. Without bpm the renderer does not
    # enable the system-header trimming used during live practice.
    engraved = render_layout(score, 1, bars, "right", total_beats=duration, bpm=68)
    engraved.layout["symbols"] = preparation_symbols()
    (folder / "layout.json").write_text(json.dumps(engraved.layout))
    (folder / "score.png").write_bytes(rasterize_score(engraved.pages[0]))
    for page, svg in enumerate(engraved.pages):
        (folder / f"page-{page}.png").write_bytes(rasterize_score(svg))


@pytest.mark.parametrize("bars", [2, 40])
def test_actual_score_transforms_keep_fixed_line_and_exact_downbeat(tmp_path, bars):
    godot = shutil.which("godot") or shutil.which("godot4")
    if not godot:
        pytest.skip("Godot 4 is unavailable")
    make_render_fixture(tmp_path, bars)
    result = subprocess.run(
        [godot, "--headless", "--path", str(ROOT / "godot"), "--script",
         str(ROOT / "tests/godot/score_motion.gd"), "--", str(tmp_path)],
        capture_output=True, text=True, timeout=40)
    assert result.returncode == 0, result.stdout[-6000:] + result.stderr
