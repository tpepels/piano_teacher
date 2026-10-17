extends SceneTree

# Live Godot checks for the board-inspired instrument surface and correctly
# earned (not simulated) presentation animations.
const Design := preload("res://practice_theme.gd")
const Stage := preload("res://game_stage.gd")
const PhaseCue := preload("res://game_phase_cue.gd")
var failures: Array[String] = []

func check(condition: bool, description: String) -> void:
    if not condition:
        failures.append(description)
        push_error("MOODBOARD_GAMEFEEL_FAIL: " + description)

func _initialize() -> void:
    _verify.call_deferred()

func _verify() -> void:
    var surface := Control.new()
    surface.size = Vector2(1024, 600)
    root.add_child(surface)
    var stage := Stage.new()
    stage.size = surface.size
    surface.add_child(stage)
    var cue := PhaseCue.new()
    cue.size = Vector2(400, 43)
    surface.add_child(cue)
    await process_frame
    var shader: ShaderMaterial = Design.notation_material()
    check(Design.STAGE.get_luminance() > .8 and
        Design.SCORE_INK.get_luminance() < .25 and
        Design.FOREST.get_luminance() < .1,
        "Sheet must be light with contrasting forest-ink vector notation")
    check(shader.shader.code.contains("vec3(0.149, 0.239, 0.204)"),
        "Engraved raster receives dark high-resolution ink, not white notes")
    var initial := {"revision":4, "transport_id":21, "hand":"left",
        "progress":.08, "running":true, "paused":false,
        "phase":"playing", "preview_only":true}
    stage.present(initial)
    check(stage.transport_active and stage.impact_energy == 0.0 and
        stage.progress_spark == 0.0,
        "Ungraded preview moves the instrument without earned hit rewards")
    var advance: Dictionary = initial.duplicate()
    advance["progress"] = .38
    stage.present(advance)
    check(stage.progress_spark >= .99 and stage.impact_energy == 0.0,
        "Real backend progress gives one short visual highlight, not fake MIDI success")
    stage._process(.16)
    check(stage.progress_spark < 1.0 and stage.progress_spark > .0
        and stage.shown_progress > .08 and stage.shown_progress <= .38,
        "Earned progress moves forward and fades without jumps")
    var faded: float = stage.progress_spark
    stage.present(advance)
    check(absf(stage.progress_spark - faded) < .0001,
        "Repeated HTTP polling cannot restart progression animation")
    var new_take: Dictionary = initial.duplicate()
    new_take["transport_id"] = 22
    new_take["progress"] = .0
    stage.present(new_take)
    check(stage.progress_spark == 0.0 and stage.shown_progress == 0.0,
        "New practice transport resets the segment rail with no success reward")
    cue.present({"loaded":true, "phase":"count_in", "mode":"practice",
        "transport_id":22})
    cue._process(.15)
    check(cue.message == "GET READY" and cue.opacity > .0,
        "Game-like cue comes from backend phase and animates once")
    print("MOODBOARD_GAMEFEEL_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
