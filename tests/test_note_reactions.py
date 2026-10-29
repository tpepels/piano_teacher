"""Native feedback follows authentic source events through the production app."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from scripts.smoke_teaching_godot import make_fixture

ROOT = Path(__file__).resolve().parents[1]
GODOT = shutil.which("godot") or shutil.which("godot4")


@pytest.mark.skipif(GODOT is None, reason="Godot 4 not installed")
def test_native_feedback_and_reaction_queues_follow_real_source_events(tmp_path):
    from piano_teacher.server import PracticeEngine

    midi = tmp_path / "chords.mid"
    make_fixture(midi)
    engine = PracticeEngine(tmp_path / "data", enable_midi=False)
    try:
        engine.load(str(midi))
        engine.plan.set_hand("both")
        payload = {"model": engine.semantic_score(),
                   "layout": engine.geometry(native_notes=True), "state": engine.state()}
    finally:
        engine.db.close()
    (tmp_path / "native.json").write_text(json.dumps(payload))
    script = tmp_path / "note_reactions.gd"
    script.write_text('''extends SceneTree
var failures: Array[String] = []

func check(ok: bool, label: String) -> void:
    if not ok:
        failures.append(label)
        print("NOTE_REACTIONS_FAIL:", label)

func _initialize() -> void:
    call_deferred("run")

func present(app: Control, state: Dictionary) -> void:
    app._on_state(0,200,PackedStringArray(),JSON.stringify(state).to_utf8_buffer())

func run() -> void:
    var app = load("FIXTURE_PATH").new()
    root.add_child(app)
    var error: String = app.load_native_fixture(OS.get_cmdline_user_args()[0])
    check(error.is_empty(), "Production native fixture loads: " + error)
    if not failures.is_empty():
        app.free()
        quit(1)
        return
    var renderer = app.practice_view.stage.renderer
    var feedback = app.practice_view.stage.feedback
    check(feedback.score == renderer and feedback.score_revision == app.revision,
        "Production binds native feedback to the loaded source revision")
    check(feedback.is_visible_in_tree(), "Native feedback is the visible presentation layer")
    var attacks: Array = []
    for event in renderer.layout.ordered_events:
        if bool(event.get("is_attack",false)) and event.get("source_id") != null:
            attacks.append(event)
    check(attacks.size() >= 3, "Imported repeated chords contain real source attacks")
    if not failures.is_empty():
        app.free()
        quit(1)
        return
    var first: Dictionary = attacks[0]
    var second: Dictionary = attacks[1]
    var later: Dictionary = attacks[-1]
    for event in [first,second,later]:
        check(feedback.source_to_id.get(str(event.source_id)) == str(event.id),
            "Native binding preserves each authentic source identity")
    renderer.present({"running":true,"hand":"both"},float(first.beat))
    await process_frame
    await process_frame
    check(renderer.drawn_noteheads.has(str(first.id)), "Production paints the first authentic notehead")
    check(feedback.note_position(str(first.id)) == renderer.drawn_noteheads[str(first.id)],
        "Feedback samples the actually painted native notehead")
    check(feedback.note_position("missing-source") == Vector2.INF,
        "Unknown source identity cannot invent a feedback position")
    var before: Vector2 = feedback.note_position(str(first.id))
    renderer.present({"running":true,"hand":"both"},float(first.beat)+.25)
    await process_frame
    await process_frame
    var after: Vector2 = feedback.note_position(str(first.id))
    check(absf(before.x-after.x-renderer.timeline.pixels_per_beat*.25) < .01 and
        absf(before.y-after.y) < .01, "Feedback follows actual native scrolling at fixed beat density")

    var state: Dictionary = app.last_state.duplicate(true)
    state.merge({"phase":"playing", "mode":"practice", "running":true,
        "paused":false, "preview_only":false, "transport_id":3,
        "feedback_marks":[{"source_id":str(second.source_id), "status":"missed"},
            {"note_id":str(later.id), "status":"early", "estimated":true}],
        "midi_visual_events":[
            {"sequence":1,"transport_id":3,"source_id":str(first.source_id),"status":"on_time","age":.02},
            {"sequence":2,"transport_id":3,"source_id":str(later.source_id),"status":"late","age":.03},
            {"sequence":3,"transport_id":3,"reference_source_id":str(second.source_id),
                "status":"unexpected","pitch":73,"age":.02}]},true)
    present(app,state)
    check(feedback.markers.get(str(second.id)) == "missed" and feedback.markers.size() == 1,
        "Only assessed exact source identities mark the native score")
    check(feedback.pulses.size() == 3 and feedback.pulses[0].id == str(first.id) and
        feedback.pulses[1].id == str(later.id) and feedback.pulses[2].id == str(second.id),
        "Native feedback maps judged attacks and unexpected input to their true source targets")
    check(app.score_effects.hit_pulses.size() == 2 and app.score_effects.wrong_ghosts.size() == 1,
        "Source event queues retain judged hits and unexpected input")
    check(app.score_effects.hit_pulses[0].note_id == str(first.id) and
        app.score_effects.hit_pulses[1].note_id == str(later.id),
        "Source queues distinguish separate attacks rather than repeated pitches")
    check(app.score_effects.hit_pulses[0].duration_ms == 220,
        "Source hit lifetime stays short and bounded")
    present(app,state)
    check(feedback.pulses.size() == 3 and app.score_effects.hit_pulses.size() == 2 and
        app.score_effects.wrong_ghosts.size() == 1, "Repeated polls cannot replay a judged event")

    # Fresh sequences with stale transport, old age or an unknown source are consumed safely.
    state.midi_visual_events = [
        {"sequence":4,"transport_id":2,"source_id":str(first.source_id),"status":"on_time","age":.01},
        {"sequence":5,"transport_id":3,"source_id":str(first.source_id),"status":"on_time","age":2.0},
        {"sequence":6,"transport_id":3,"source_id":"missing-source","status":"on_time","age":.01}]
    present(app,state)
    check(feedback.pulses.size() == 3 and app.score_effects.hit_pulses.size() == 2,
        "Stale or unmapped events cannot create a native reward")
    for ungraded_mode in ["preview", "listen"]:
        state.preview_only = ungraded_mode == "preview"
        state.mode = "listen" if ungraded_mode == "listen" else "practice"
        state.transport_id += 1
        var sequence: int = 7 if ungraded_mode == "preview" else 8
        state.midi_visual_events = [{"sequence":sequence,"transport_id":state.transport_id,
            "source_id":str(first.source_id),"status":"on_time","age":.01}]
        present(app,state)
        check(feedback.markers.is_empty() and feedback.pulses.is_empty(),
            ungraded_mode + " clears native assessed feedback")
        check(app.score_effects.hit_pulses.is_empty() and app.score_effects.wrong_ghosts.is_empty(),
            ungraded_mode + " cannot retain or award source hit credit")
        state.preview_only = false
        state.mode = "practice"
        state.feedback_marks = []
        present(app,state)
        check(feedback.pulses.is_empty() and app.score_effects.hit_pulses.is_empty(),
            "Returning to graded practice cannot replay " + ungraded_mode + " events")

    var groups: Array = load("res://living_score.gd").groups_crossed(
        app.living_chords,float(first.beat)-.01,float(first.beat)+.01)
    var chord_notes := 0
    for event in attacks:
        if absf(float(event.beat)-float(first.beat)) < .001:
            chord_notes += 1
    check(groups.size() == 1 and groups[0].notes.size() == chord_notes,
        "Crossing an authentic source onset groups the entire chord exactly once")
    app._preview_note_arrivals(groups)
    check(app.score_effects.preview_pulses.size() == chord_notes and
        app.score_effects.preview_pulses[0].status == "preview" and
        app.score_effects.hit_pulses.is_empty() and feedback.pulses.is_empty(),
        "Preview source arrivals remain distinct from assessed native rewards")
    check(app.practice_view.stage.effects.impact_energy == 0.0 and app.practice_view.stage.effects.preview_energy > 0.0,
        "Ungraded source arrivals illuminate the stage without earned success")
    app._clear_assessed_effects_in_ungraded_mode({"preview_only":false,"mode":"practice"})
    check(app.score_effects.preview_pulses.is_empty(),
        "Returning to a scored take clears its ungraded source effects")
    renderer.queue_redraw()
    feedback.queue_redraw()
    await process_frame
    await process_frame
    print("NOTE_REACTIONS_FAILURES:",failures.size())
    app.free()
    quit(0 if failures.is_empty() else 1)
'''.replace("FIXTURE_PATH", str(ROOT / "tests/godot/native_production_fixture.gd")))
    result = subprocess.run(
        [GODOT, "--headless", "--path", str(ROOT / "godot"),
         "--script", str(script), "--", str(tmp_path)],
        capture_output=True, text=True, timeout=30
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "SCRIPT ERROR" not in output and "ERROR:" not in output, output
    assert "NOTE_REACTIONS_FAILURES:0" in output, output
