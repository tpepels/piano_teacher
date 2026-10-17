extends SceneTree

# Live Godot checks for the board-inspired instrument surface and correctly
# earned (not simulated) presentation animations.
const Design := preload("res://practice_theme.gd")
const Stage := preload("res://game_stage.gd")
const PhaseCue := preload("res://game_phase_cue.gd")
const ImpactCallout := preload("res://game_impact_callout.gd")
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
    check(Design.STAGE.get_luminance() < .25 and
        Design.SCORE_INK.get_luminance() > .8 and
        Design.FOREST.get_luminance() < .1,
        "Sheet must retain contrasting luminous notation on a dark stage")
    check(shader.shader.code.contains("vec3(0.918, 0.957, 0.929)"),
        "Engraved raster receives luminous high-resolution ink")
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
    check(stage.milestone_light == 0.0 and stage.milestone_slot == -1,
        "Preview visual progress cannot produce an earned milestone celebration")
    check(absf(stage.progress_spark - faded) < .0001,
        "Repeated HTTP polling cannot restart progression animation")
    var new_take: Dictionary = initial.duplicate()
    new_take["transport_id"] = 22
    new_take["progress"] = .0
    stage.present(new_take)
    check(stage.progress_spark == 0.0 and stage.shown_progress == 0.0,
        "New practice transport resets the segment rail with no success reward")
    # Only backend-provided, graded progress may light the milestone.
    var scored := initial.duplicate()
    scored["preview_only"] = false
    scored["loaded"] = true
    scored["mode"] = "practice"
    scored["transport_id"] = 23
    scored["progress"] = 0.0
    stage.present(scored)
    scored["progress"] = .22
    stage.present(scored)
    check(stage.milestone_slot == 0 and stage.milestone_light > .0,
        "A scored fifth of the exercise gets a short progress celebration")
    stage._process(.22)
    var milestone_after: float = stage.milestone_light
    stage.present(scored)
    check(absf(stage.milestone_light - milestone_after) < .001,
        "Polling the same progress must not restart the milestone glow")
    var impact := ImpactCallout.new()
    surface.add_child(impact)
    impact.size = Vector2(230, 60)
    impact.react("on_time", 1000)
    check(impact.message == "RIGHT ON TIME" and impact.elapsed == 0.0,
        "Only a received on-time judgment creates a coaching card")
    impact._process(.25)
    var elapsed_after: float = impact.elapsed
    impact.react("on_time", 1050)
    check(absf(impact.elapsed-elapsed_after) < .0001,
        "Chord attacks in the same instant cannot spam competing cards")
    impact.react("late", 1250)
    check(impact.message == "A LITTLE LATE" and impact.tone != Design.SCORE_ACCENT,
        "Timing errors get a distinct, supportive visual reaction")
    impact.clear()
    check(impact.elapsed >= ImpactCallout.DURATION,
        "Entering ungraded playback removes an old success message")
    cue.present({"loaded":true, "phase":"count_in", "mode":"practice",
        "transport_id":22})
    cue._process(.15)
    check(cue.message == "GET READY" and cue.opacity > .0,
        "Game-like cue comes from backend phase and animates once")
    print("MOODBOARD_GAMEFEEL_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
