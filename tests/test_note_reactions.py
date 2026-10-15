"""7.6b: real Godot glyph-aligned cues and MIDI-triggered reactions."""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
GODOT = shutil.which("godot") or shutil.which("godot4")


@pytest.mark.skipif(GODOT is None, reason="Godot 4 not installed")
def test_notehead_outlines_and_reactions_use_real_score_mapping(tmp_path):
    script = tmp_path / "note_reactions.gd"
    script.write_text('''extends SceneTree
const Ink := preload("res://notehead_ink.gd")

class FixtureApp extends "res://main.gd":
    func _ready() -> void:
        _build_interface()
        _navigate("practice")
        set_process(false)

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    # Rotated notehead outlines are closed, wider than tall, and remain
    # centred on the exact Verovio x/y rather than nearby system positions.
    var center := Vector2(80, 40)
    var radii: Vector2 = Ink.radii(18)
    assert(radii.x > radii.y)
    var ellipse: PackedVector2Array = Ink.ellipse(center, radii.x, radii.y)
    assert(ellipse.size() == 33 and ellipse[0].distance_to(ellipse[-1]) < .01)
    var bounds := Rect2(center, Vector2.ZERO)
    for point in ellipse:
        bounds = bounds.expand(point)
    assert(bounds.size.x > bounds.size.y)
    assert(bounds.size.x < 40 and bounds.size.y < 30)

    var app := FixtureApp.new()
    root.add_child(app)
    await process_frame
    app.revision = 9
    app.layout_revision = 9
    app.last_seen_midi_visual_sequence = 0
    app.score_layout = {"attack_map":{"a":"na", "b":"nb", "c":"nc"}, "notes":[
        {"id":"na", "page":0, "x":.32, "y":.52},
        {"id":"nb", "page":0, "x":.32, "y":.47},
        {"id":"nc", "page":0, "x":.58, "y":.52}]}
    app.score_overlay.image_size = Vector2(1200, 240)
    app.score_overlay.active_page = 0
    app.score_overlay.staff_gap_fraction = .04
    app.score_overlay.size = Vector2(1200, 240)
    app.note_reactions.size = Vector2(1200, 240)
    app.note_reactions.staff_gap_fraction = .04
    app.living_chords = [{"beat":0.0, "notes":[
        {"id":"na", "page":0, "x":.32, "y":.52, "pitch":60, "hand":"right"},
        {"id":"nb", "page":0, "x":.32, "y":.47, "pitch":64, "hand":"right"}]}]
    app.last_state = {"phase":"ready", "running":false, "mode":"practice",
        "play_from_beat":0.0}
    app._process(.016)
    assert(app.score_overlay.next_chord.size() == 2,
        "Ready stage must highlight the next real chord before Play")
    app.last_state["phase"] = "feedback"
    app._process(.016)
    assert(app.score_overlay.next_chord.is_empty(),
        "Feedback must not overwrite judged notes with a fresh teal cue")
    app.score_overlay.next_chord = [
        {"id":"na", "page":0, "x":.32, "y":.52, "emphasis":1.0},
        {"id":"nb", "page":0, "x":.32, "y":.47, "emphasis":1.0}]
    app.score_overlay.marks = [
        {"note_id":"nb", "page":0, "x":.32, "y":.47, "status":"missed"}]
    var state := {"phase":"playing", "transport_id":3, "midi_visual_events":[
        {"sequence":1,"transport_id":3,"source_id":"a","status":"on_time","age":.02},
        {"sequence":2,"transport_id":3,"source_id":"c","status":"late","age":.03},
        {"sequence":3,"transport_id":3,"reference_source_id":"b","status":"unexpected",
            "pitch":73,"age":.02}]}
    app._consume_live_piano_hits(state)
    assert(app.score_overlay.hit_pulses.size() == 2)
    assert(app.note_reactions.hit_pulses.size() == 2,
        "Score reaction underlay must own the live pulse array")
    assert(app.score_overlay.hit_pulses[0].x == .32)
    assert(app.score_overlay.hit_pulses[1].x == .58)
    assert(app.score_overlay.hit_pulses[0].duration_ms == 260)
    assert(app.score_overlay.wrong_ghosts.size() == 1)
    assert(app.score_overlay.wrong_ghosts[0].y == .47,
        "Wrong pitch must point to the true expected note, not a fake glyph")
    assert(not app.score_overlay.wrong_ghosts[0].has("label"),
        "No extra wrong-pitch text on the music")
    app._consume_live_piano_hits(state)
    assert(app.score_overlay.hit_pulses.size() == 2, "Repeated poll must not duplicate pulses")
    # Drawing the same score and reaction transform must parse and render
    # without any separate positioning / type-inference errors.
    app.score_overlay.queue_redraw()
    app.note_reactions.queue_redraw()
    await process_frame
    await process_frame
    print("NOTE_REACTIONS_OK")
    quit()
''')
    result = subprocess.run(
        [GODOT, "--headless", "--path", str(ROOT / "godot"),
         "--script", str(script)],
        capture_output=True, text=True, timeout=30
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "SCRIPT ERROR" not in output, output
    assert "NOTE_REACTIONS_OK" in output, output
