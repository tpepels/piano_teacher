extends SceneTree

const Design := preload("res://practice_theme.gd")

# Phase 7.9: all light is driven by real backend-sourced state/events.
# There is no score grading, fake MIDI input, or additional transport UI.
class FixtureApp extends "res://main.gd":
    func _ready() -> void:
        _build_interface()
        resized.connect(_update_responsive_layout)
        _update_responsive_layout()
        set_process(false)

var failures: Array[String] = []

func check(ok: bool, message: String) -> void:
    if not ok:
        failures.append(message)
        print("PHASE79_FAIL:", message)

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var Lamp = load("res://game_input_indicator.gd")
    var Stage = load("res://game_stage.gd")
    check(Lamp != null and Stage != null, "7.9 UI modules load in Godot")
    if Lamp == null or Stage == null:
        quit(1)
        return
    var lamp = Lamp.new()
    root.add_child(lamp)
    lamp.size = Vector2(150, 29)
    lamp.present({"device":"", "midi_input_count":0,
        "midi_input_age":null, "preview_only":true})
    check(not lamp.connected and lamp.label == "NO PIANO",
        "Disconnected practice must have readable status instead of success glow")
    check(lamp.activity == 0, "Disconnected LED is not MIDI activity")
    lamp.present({"device":"Kawai CA-49", "midi_input_count":22,
        "midi_input_age":.12, "preview_only":false})
    check(lamp.connected and lamp.label == "MIDI CONNECTED",
        "Connection is visible without navigating to Settings")
    check(lamp.activity == 0,
        "An old MIDI count on startup cannot fabricate a new note arrival")
    lamp.present({"device":"Kawai CA-49", "midi_input_count":23,
        "midi_input_age":.04, "preview_only":false})
    check(lamp.activity == 1.0, "A real MIDI attack briefly lights the LED")
    lamp._process(.2)
    var faded: float = lamp.activity
    lamp.present({"device":"Kawai CA-49", "midi_input_count":23,
        "midi_input_age":.09, "preview_only":false})
    check(lamp.activity == faded, "State polling alone never restarts the LED")
    lamp._process(2.0)
    check(lamp.activity == 0, "MIDI lamp expires rather than staying stuck on")
    lamp.present({"device":"Kawai CA-49", "midi_input_count":25,
        "midi_input_age":.07, "preview_only":true})
    check(lamp.label == "PREVIEW",
        "Ungraded preview is labelled without claiming scored playback")
    lamp.present({"device":"", "midi_input_count":25,
        "midi_input_age":null, "preview_only":false})
    check(lamp.label == "NO PIANO" and lamp.activity == 0,
        "USB disconnect cannot inherit the last note's light")
    lamp.present({"device":"Another MIDI keyboard", "midi_input_count":40,
        "midi_input_age":.03, "preview_only":false})
    check(lamp.activity == 0 and lamp.label == "MIDI CONNECTED",
        "Selecting a different keyboard cannot replay an old attack")
    lamp.present({"device":"Another MIDI keyboard", "midi_input_count":41,
        "midi_input_age":.02, "preview_only":false})
    check(lamp.activity == 1,
        "A subsequent physical attack from the new piano lights the indicator")

    var stage = Stage.new()
    root.add_child(stage)
    stage.size = Vector2(1200, 680)
    var ready := {"loaded":true, "title":"Piece", "phase":"ready",
        "mode":"practice", "transport_id":3, "hand":"left",
        "running":false, "preview_only":false, "progress":.4,
        "take_result":null}
    stage.present(ready)
    check(stage.result_wave == 0, "Ready status cannot trigger celebration")
    var preview := ready.duplicate(true)
    preview["phase"] = "feedback"
    preview["preview_only"] = true
    preview["take_result"] = {"clean":true, "correct":10}
    stage.present(preview)
    check(stage.result_wave == 0,
        "Clean-looking data from an ungraded preview must not trigger a result wave")
    var result := ready.duplicate(true)
    result["phase"] = "feedback"
    result["take_result"] = {"clean":true, "correct":10}
    stage.present(result)
    check(stage.result_wave == 1.0 and stage.result_tone == Design.SCORE_ACCENT,
        "A real clean feedback result begins the teal success wave")
    stage._process(.27)
    var energy: float = stage.result_wave
    stage.present(result)
    check(absf(stage.result_wave - energy) < .00001,
        "Repeated /state responses cannot restart an assessed result animation")
    var stopped := result.duplicate(true)
    stopped["phase"] = "ready"
    stage.present(stopped)
    stage.present(result)
    check(absf(stage.result_wave - energy) < .00001,
        "Returning to the same result never invents a second celebration")
    var failure := result.duplicate(true)
    failure["transport_id"] = 4
    failure["take_result"] = {"clean":false, "correct":6}
    stage.present(failure)
    check(stage.result_wave == 1.0 and stage.result_tone == Color("#BC5A50"),
        "Next assessed failed take shows a distinct coral wave")
    stage._process(3.0)
    check(stage.result_wave == 0, "Result wave expires and leaves score unobscured")
    var listen := failure.duplicate(true)
    listen["mode"] = "listen"
    listen["transport_id"] = 5
    listen["take_result"] = {"clean":true}
    stage.present(listen)
    check(stage.result_wave == 0, "Listen cannot trigger a clean-take wave")

    root.mode = Window.MODE_WINDOWED
    root.size = Vector2i(1024, 768)
    var app := FixtureApp.new()
    app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root.add_child(app)
    await process_frame
    await process_frame
    check(app.game_input_indicator.get_parent() == app.speed_label.get_parent(),
        "Activity lamp belongs beside BPM/hand, not over engraved music")
    check(app.game_input_indicator.get_combined_minimum_size().x >= 130,
        "Live MIDI status must remain readable")
    check(app.practice_controls.get_child_count() == 3,
        "New gaming cues must not introduce a fourth transport button")
    check(app.score_frame.get_global_rect().end.x <= 1026.0,
        "The music stage must not overflow a normal laptop viewport")
    print("PHASE79_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
