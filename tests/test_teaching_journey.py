"""The real learner path must connect imported notes, hints and musical time."""
import os
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from scripts.smoke_teaching_godot import make_fixture, require_clean_log, run

ROOT = Path(__file__).resolve().parents[1]


def test_teaching_journey_rejects_native_fallback_warning():
    with pytest.raises(RuntimeError,match="Native notation fallback"):
        require_clean_log("WARNING: Native notation fallback: Missing engraved Verovio chord")


@pytest.mark.parametrize("harness",["teaching_journey","live_playback"])
def test_journey_fixture_tracks_native_noteheads_and_revision_without_http(tmp_path,harness):
    godot=shutil.which("godot") or shutil.which("godot4")
    if not godot:
        pytest.skip("Godot unavailable")
    from piano_teacher.server import PracticeEngine
    midi=tmp_path/"chords.mid"
    make_fixture(midi)
    engine=PracticeEngine(tmp_path/"data",enable_midi=False)
    try:
        engine.load(str(midi))
        engine.plan.set_hand("both")
        model=engine.semantic_score()
        layout=engine.geometry(native_notes=True)
    finally:
        engine.db.close()
    payload=tmp_path/"native.json"
    payload.write_text(json.dumps({"model":model,"layout":layout}))
    runner=tmp_path/"native_coordinates.gd"
    position_call="note_position()" if harness=="teaching_journey" else "note_position(note)"
    runner.write_text('''extends "HARNESS"
class FixtureApp extends Control:
    var native_notation_enabled := true
    var timeline_preview: Control
    var score_layout: Dictionary
    var score_crop_origin := Vector2.ZERO
    var score_crop_size := Vector2.ONE
    var score_content := Control.new()
    var score_view := TextureRect.new()
    var revision := 11
    var layout_revision := 11
    var rendered_revision := 11
    var timeline_model_revision := 11
    var layout_pending := false
    var score_pending := false

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var payload: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
        OS.get_cmdline_user_args()[0]))
    var fixture := FixtureApp.new()
    app = fixture
    root.add_child(fixture)
    fixture.add_child(fixture.score_content)
    fixture.add_child(fixture.score_view)
    fixture.score_content.size = Vector2(200,200)
    fixture.score_view.texture = ImageTexture.create_from_image(
        Image.create(2,2,false,Image.FORMAT_RGBA8))
    fixture.score_layout = payload["layout"]
    fixture.timeline_preview = load("res://notation/native/view.gd").new()
    fixture.add_child(fixture.timeline_preview)
    var renderer = fixture.timeline_preview
    renderer.position = Vector2(83,47)
    renderer.size = Vector2(1200,500)
    var layout: Dictionary = payload["layout"]
    check(renderer.set_verovio_glyphs(layout["native_glyphs"],
        layout["native_note_templates"],layout["native_tie_templates"],
        layout["native_chord_templates"],layout["native_beam_fragments"],
        layout["native_tuplet_fragments"],layout["native_slur_fragments"],
        layout["native_required_slur_pairs"],layout["native_slurs_complete"],
        layout["native_required_beam_groups"],layout["native_beams_complete"]),
        "Authentic fragment atlas loads")
    check(renderer.load_score(payload["model"]),"Real model remains native")
    renderer.present({"running":true,"hand":"both"},0.0)
    await process_frame
    await process_frame
    var note: Dictionary = fixture.score_layout["notes"][0]
    tracked_id = str(note["id"])
    check(renderer.drawn_noteheads.has(tracked_id),"Actual source head was painted")
    var expected: Vector2 = renderer.get_global_transform_with_canvas() * renderer.drawn_noteheads[tracked_id]
    check(POSITION.distance_to(expected) < .01,"Fixture samples actual native notehead coordinates")
    check(score_ready(),"Matching native revision is ready")
    fixture.timeline_model_revision -= 1
    check(not score_ready(),"Previous native revision cannot satisfy score_ready")
    fixture.timeline_model_revision += 1
    renderer.native_ready = false
    check(not score_ready(),"Raster readiness cannot hide a native fallback")
    renderer.native_ready = true
    renderer.present({"running":true,"hand":"both"},20.0)
    await process_frame
    await process_frame
    check(POSITION.distance_to(expected-Vector2(renderer.timeline.pixels_per_beat*20.0,0)) < .01,
        "Tracked native note keeps its exact beat position after leaving the viewport")
    print("NATIVE_FIXTURE_FAILURES:",failures.size())
    fixture.free()
    quit(0 if failures.is_empty() else 1)
'''.replace("HARNESS",str(ROOT/"tests"/"godot"/f"{harness}.gd"))
       .replace("POSITION",position_call))
    result=subprocess.run([godot,"--headless","--path",str(ROOT/"godot"),
        "--script",str(runner),"--",str(payload)],capture_output=True,text=True,
        env={**os.environ,"PIANO_TEACHER_NATIVE_NOTATION":"1"},timeout=45)
    output=result.stdout+result.stderr
    assert result.returncode==0,output
    assert "NATIVE_FIXTURE_FAILURES:0" in output
    assert "SCRIPT ERROR" not in output and "Parse Error" not in output
    assert "ERROR:" not in output and "Native notation fallback:" not in output


def test_imported_midi_guided_hints_and_real_practice_keep_mastery_honest(tmp_path,monkeypatch):
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        pytest.skip("Rendered teaching journey requires a graphical desktop")
    if not (shutil.which("godot") or shutil.which("godot4")):
        pytest.skip("Godot unavailable")
    monkeypatch.setenv("PIANO_TEACHER_NATIVE_NOTATION","1")
    result = run(tmp_path)
    assert result["failures"] == []
    assert result["renderer"] != "headless"
    hint = next(frame for frame in result["frames"] if frame["frame"] == "wrong-note-hint.png")
    assert hint["painted_expected_keys"] == 3
    assert hint["notehead_ink"] >= 8
    assert all(frame["native_ready"] and frame["native_visible"]
               for frame in result["frames"])
    first, last = [frame for frame in result["frames"] if frame["frame"].startswith("practice-playing-")]
    assert last["note_x"] < first["note_x"] - 10
