"""Real bundled MIDI studies and imported MIDI must retain constant travel."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from piano_teacher.notation.lesson import build_lesson_score
from piano_teacher.music import Note, Phrase
from piano_teacher.warmups import materialize

ROOT = Path(__file__).resolve().parents[1]


def write_native_fixture(folder, source, hand="both", bpm=80):
    """Use the production preparation path; no HTTP server or raster pages."""
    from piano_teacher.server import PracticeEngine

    engine = PracticeEngine(folder / "engine", enable_midi=False)
    try:
        engine.load(str(source), warmup=True)
        engine._prepare_perform(scope="whole")
        engine.plan.set_hand(hand)
        engine.plan.variant_index = len(engine.plan.variants) - 1
        engine.plan.bpm = bpm
        # Interaction snapshots use one stable initial revision.
        engine.score_revision = 1
        model = engine.semantic_score()
        layout = engine.geometry(native_notes=True)
        state = engine.state()
        assert model["revision"] == layout["revision"] == state["revision"]
        assert model["notes"] and layout["native_note_templates"]
        (folder / "native.json").write_text(json.dumps({
            "model": model, "layout": layout, "state": state}))
        return model, layout
    finally:
        engine.db.close()


def make_phrase_fixture(folder, phrase, *, boundaries=None, time_signatures=(), hand="both", bpm=80):
    notation = build_lesson_score(phrase, boundaries=boundaries,
                                  time_signatures=time_signatures)
    source = folder / "source.musicxml"
    source.write_text(notation.musicxml)
    return write_native_fixture(folder, source, hand, bpm)


def make_midi_fixture(folder, slug="chords", hand="left", bpm=80):
    source = materialize("warmup:" + slug, folder / "midi")
    return write_native_fixture(folder, source, hand, bpm)


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
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "SCRIPT ERROR" not in output, output
    assert "SCORE_MOTION_FAILURES:0" in output, output


def test_short_ornament_intervals_cannot_disable_proportional_spacing(tmp_path):
    godot = shutil.which("godot") or shutil.which("godot4")
    if not godot:
        pytest.skip("Godot 4 unavailable")
    notes = (Note(0, .1166666667, 82, 0, 0), Note(.11875, .2375, 81, 0, 0),
             Note(.2375, .4875, 79, 0, 0), Note(.5, 1, 81, 0, 0)) + tuple(
        Note(i, i + .5, 77, 0, 0) for i in range(1, 6))
    phrase = Phrase(1, 1, 2, 0, 6, notes)
    make_phrase_fixture(tmp_path, phrase, boundaries=(0, 3, 6),
                        time_signatures=((0,3,4),), hand="right")
    result = subprocess.run([godot, "--headless", "--path", str(ROOT / "godot"),
                             "--script", str(ROOT / "tests/godot/score_motion.gd"),
                             "--", str(tmp_path)], capture_output=True, text=True, timeout=60)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "SCRIPT ERROR" not in output, output
    assert "SCORE_MOTION_FAILURES:0" in output, output


def test_tied_chords_and_rests_keep_constant_travel_across_measures(tmp_path):
    godot = shutil.which("godot") or shutil.which("godot4")
    if not godot:
        pytest.skip("Godot 4 unavailable")
    from test_reading_spacing import reading_phrase
    phrase = reading_phrase(bars=8)
    model, _ = make_phrase_fixture(tmp_path, phrase)
    assert len(model["measures"]) == 8
    assert any(event["kind"] == "rest" for event in model["notation_events"])
    assert any(event.get("tie_start") or event.get("tie_stop")
               for event in model["notation_events"])
    result = subprocess.run([godot, "--headless", "--path", str(ROOT / "godot"),
                             "--script", str(ROOT / "tests/godot/score_motion.gd"),
                             "--", str(tmp_path)], capture_output=True, text=True, timeout=60)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "SCRIPT ERROR" not in output, output
    assert "SCORE_MOTION_FAILURES:0" in output, output


def test_meter_change_preserves_context_without_disabling_constant_spacing(tmp_path):
    godot = shutil.which("godot") or shutil.which("godot4")
    if not godot:
        pytest.skip("Godot 4 unavailable")
    grid = (0, 3, 6, 10, 14)
    phrase = Phrase(1, 1, 4, 0, 14, tuple(
        Note(i, i + .8, 72 if hand == "right" else 48, 0, 0, hand)
        for i in range(14) for hand in ("right", "left")))
    model, _ = make_phrase_fixture(tmp_path, phrase, boundaries=grid,
                                   time_signatures=((0,3,4),(6,4,4)))
    assert len({tuple(measure["meter"]) for measure in model["measures"]}) == 2
    result = subprocess.run([godot, "--headless", "--path", str(ROOT / "godot"),
                             "--script", str(ROOT / "tests/godot/score_motion.gd"),
                             "--", str(tmp_path)], capture_output=True, text=True, timeout=60)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "SCRIPT ERROR" not in output, output
    assert "SCORE_MOTION_FAILURES:0" in output, output
