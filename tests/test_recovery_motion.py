"""Real bundled MIDI studies and imported MIDI must retain constant travel."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from piano_teacher.lesson_score import build_lesson_score
from piano_teacher.music import Note, Phrase, load_midi
from piano_teacher.notation_symbols import preparation_symbols
from piano_teacher.raster import rasterize_score
from piano_teacher.score import render_layout
from piano_teacher.warmups import materialize

ROOT = Path(__file__).resolve().parents[1]


def make_midi_fixture(folder, slug="chords", hand="left", bpm=80):
    piece = load_midi(materialize("warmup:" + slug, folder / "midi"))
    end = piece.bar_boundaries[-1]
    notes = tuple(n for n in piece.notes if hand == "both" or n.hand == hand)
    phrase = Phrase(1, 1, len(piece.bar_boundaries) - 1, 0, end, notes)
    lesson = build_lesson_score(phrase, boundaries=piece.bar_boundaries)
    score = render_layout(lesson, 1, phrase.last_bar, hand, total_beats=end, bpm=bpm)
    score.layout["symbols"] = preparation_symbols()
    (folder / "layout.json").write_text(json.dumps(score.layout))
    for page, svg in enumerate(score.pages):
        data = rasterize_score(svg)
        (folder / f"page-{page}.png").write_bytes(data)
        if page == 0:
            (folder / "score.png").write_bytes(data)


@pytest.mark.parametrize("slug,hand", [("chords", "left"), ("classical-melody", "both"),
                                      ("jazz-phrasing", "right")])
def test_real_midi_passage_has_constant_motion(tmp_path, slug, hand):
    godot = shutil.which("godot") or shutil.which("godot4")
    if not godot:
        pytest.skip("Godot 4 unavailable")
    make_midi_fixture(tmp_path, slug, hand)
    result = subprocess.run([godot, "--headless", "--path", str(ROOT / "godot"),
                             "--script", str(ROOT / "tests/godot/score_motion.gd"),
                             "--", str(tmp_path)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout[-7000:] + result.stderr


def test_short_ornament_intervals_cannot_disable_proportional_spacing(tmp_path):
    godot = shutil.which("godot") or shutil.which("godot4")
    if not godot:
        pytest.skip("Godot 4 unavailable")
    notes = (Note(0, .1166666667, 82, 0, 0), Note(.11875, .2375, 81, 0, 0),
             Note(.2375, .4875, 79, 0, 0), Note(.5, 1, 81, 0, 0)) + tuple(
        Note(i, i + .5, 77, 0, 0) for i in range(1, 6))
    phrase = Phrase(1, 1, 2, 0, 6, notes)
    score = render_layout(build_lesson_score(phrase, boundaries=(0, 3, 6)),
                         1, 2, "right", total_beats=6, bpm=80)
    score.layout["symbols"] = preparation_symbols()
    (tmp_path / "layout.json").write_text(json.dumps(score.layout))
    for page, svg in enumerate(score.pages):
        data = rasterize_score(svg)
        (tmp_path / f"page-{page}.png").write_bytes(data)
        if page == 0:
            (tmp_path / "score.png").write_bytes(data)
    result = subprocess.run([godot, "--headless", "--path", str(ROOT / "godot"),
                             "--script", str(ROOT / "tests/godot/score_motion.gd"),
                             "--", str(tmp_path)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout[-7000:] + result.stderr


def test_tied_chords_and_rests_keep_constant_travel_across_systems(tmp_path):
    godot = shutil.which("godot") or shutil.which("godot4")
    if not godot:
        pytest.skip("Godot 4 unavailable")
    from test_reading_spacing import reading_phrase
    phrase = reading_phrase(bars=8)
    score = render_layout(build_lesson_score(phrase), 1, 8, "both", total_beats=32, bpm=80)
    assert len(score.layout["systems"]) > 1
    assert any('class="tie"' in svg for svg in score.pages)
    score.layout["symbols"] = preparation_symbols()
    (tmp_path / "layout.json").write_text(json.dumps(score.layout))
    for page, svg in enumerate(score.pages):
        data = rasterize_score(svg)
        (tmp_path / f"page-{page}.png").write_bytes(data)
        if page == 0:
            (tmp_path / "score.png").write_bytes(data)
    result = subprocess.run([godot, "--headless", "--path", str(ROOT / "godot"),
                             "--script", str(ROOT / "tests/godot/score_motion.gd"),
                             "--", str(tmp_path)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout[-7000:] + result.stderr


def test_meter_change_preserves_context_without_disabling_constant_spacing(tmp_path):
    godot = shutil.which("godot") or shutil.which("godot4")
    if not godot:
        pytest.skip("Godot 4 unavailable")
    grid = (0, 3, 6, 10, 14)
    phrase = Phrase(1, 1, 4, 0, 14, tuple(
        Note(i, i + .8, 72 if hand == "right" else 48, 0, 0, hand)
        for i in range(14) for hand in ("right", "left")))
    score = render_layout(build_lesson_score(phrase, boundaries=grid,
        time_signatures=((0, 3, 4), (6, 4, 4))), 1, 4, "both", total_beats=14, bpm=80)
    assert score.layout["strip_trim_repeated_headers"] is False
    score.layout["symbols"] = preparation_symbols()
    (tmp_path / "layout.json").write_text(json.dumps(score.layout))
    for page, svg in enumerate(score.pages):
        data = rasterize_score(svg)
        (tmp_path / f"page-{page}.png").write_bytes(data)
        if page == 0:
            (tmp_path / "score.png").write_bytes(data)
    result = subprocess.run([godot, "--headless", "--path", str(ROOT / "godot"),
                             "--script", str(ROOT / "tests/godot/score_motion.gd"),
                             "--", str(tmp_path)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout[-7000:] + result.stderr
