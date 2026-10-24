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
        state=engine.state()
    finally:
        engine.db.close()
    payload=tmp_path/"native.json"
    payload.write_text(json.dumps({"model":model,"layout":layout,"state":state}))
    runner=tmp_path/"native_coordinates.gd"
    position_call="note_position()" if harness=="teaching_journey" else "note_position(note)"
    runner.write_text('''extends "HARNESS"
func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var payload: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
        OS.get_cmdline_user_args()[0]))
    var fixture = load("NATIVE_FIXTURE_PATH").new()
    app = fixture
    root.add_child(fixture)
    check(fixture.load_native_fixture(OS.get_cmdline_user_args()[0].get_base_dir()).is_empty(),
        "Production handlers bind authentic assets and source model")
    if not failures.is_empty():
        fixture.free()
        quit(1)
        return
    var renderer = fixture.timeline_preview
    renderer.set_anchors_and_offsets_preset(Control.PRESET_TOP_LEFT)
    renderer.position = Vector2(83,47)
    renderer.size = Vector2(1200,500)
    renderer.present({"running":true,"hand":"both"},0.0)
    await process_frame
    await process_frame
    var note: Dictionary = fixture.score_layout["notes"][0]
    tracked_id = str(note["id"])
    check(renderer.drawn_noteheads.has(tracked_id),"Actual source head was painted")
    if not failures.is_empty():
        fixture.free()
        quit(1)
        return
    var expected: Vector2 = renderer.get_global_transform_with_canvas() * renderer.drawn_noteheads[tracked_id]
    check(POSITION.distance_to(expected) < .01,"Fixture samples actual native notehead coordinates")
    check(score_ready(),"Matching native revision is ready")
    for property in ["revision", "layout_revision", "timeline_model_revision", "rendered_revision"]:
        var current: int = fixture.get(property)
        fixture.set(property,current-1)
        check(not score_ready(),"Stale " + property + " cannot satisfy score_ready")
        fixture.set(property,current)
        check(score_ready(),"Restoring " + property + " restores native readiness")
    for property in ["layout_pending", "timeline_model_pending"]:
        fixture.set(property,true)
        check(not score_ready(),"Pending " + property + " cannot satisfy score_ready")
        fixture.set(property,false)
    renderer.hide()
    check(not score_ready(),"Hidden production view cannot satisfy visible readiness")
    renderer.show()
    renderer.clear_score()
    check(not fixture._native_score_ready(),"Cleared native model invalidates production readiness")
    check(not score_ready(),"Cleared native model cannot satisfy journey readiness")
    fixture._on_timeline_model(0,200,PackedStringArray(),
        JSON.stringify(payload["model"]).to_utf8_buffer())
    check(score_ready(),"Production model handler restores real native readiness after clear")
    renderer.present({"running":true,"hand":"both"},20.0)
    await process_frame
    await process_frame
    check(POSITION.distance_to(expected-Vector2(renderer.timeline.pixels_per_beat*20.0,0)) < .01,
        "Tracked native note keeps its exact beat position after leaving the viewport")
    print("NATIVE_FIXTURE_FAILURES:",failures.size())
    fixture.free()
    quit(0 if failures.is_empty() else 1)
'''.replace("HARNESS",str(ROOT/"tests"/"godot"/f"{harness}.gd"))
       .replace("NATIVE_FIXTURE_PATH",str(ROOT/"tests"/"godot"/"native_production_fixture.gd"))
       .replace("POSITION",position_call))
    result=subprocess.run([godot,"--headless","--path",str(ROOT/"godot"),
        "--script",str(runner),"--",str(payload)],capture_output=True,text=True,
        env={key:value for key,value in os.environ.items() if key not in
             {"PIANO_TEACHER_NATIVE_NOTATION","PIANO_TEACHER_RENDERER",
              "PIANO_TEACHER_TIMELINE_PREVIEW"}},timeout=45)
    output=result.stdout+result.stderr
    assert result.returncode==0,output
    assert "NATIVE_FIXTURE_FAILURES:0" in output,output
    assert "SCRIPT ERROR" not in output and "Parse Error" not in output
    assert "ERROR:" not in output and "Native notation fallback:" not in output


def test_imported_midi_guided_hints_and_real_practice_keep_mastery_honest(tmp_path):
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        pytest.skip("Rendered teaching journey requires a graphical desktop")
    if not (shutil.which("godot") or shutil.which("godot4")):
        pytest.skip("Godot unavailable")
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
