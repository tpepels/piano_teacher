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
    # Fixed-width status controls used to lose the final D despite passing
    # the old arbitrary minimum-width assertion. Measure the actual font
    # after normal responsive containers have assigned the control's width.
    for dimensions in [Vector2i(1536, 960), Vector2i(1024, 768), Vector2i(800, 600)]:
        root.size = dimensions
        await process_frame
        await process_frame
        var indicator: Control = app.game_input_indicator
        indicator.present({"device": "Kawai CA-49", "preview_only": false})
        var label_width: float = indicator.get_theme_font("font").get_string_size(
            "MIDI CONNECTED", HORIZONTAL_ALIGNMENT_LEFT, -1, 13).x
        print("PHASE79_STATUS_WIDTH: window=", dimensions, " control=", indicator.size.x,
            " text=", label_width)
        check(indicator.size.x - 32.0 >= ceilf(label_width),
            "Complete MIDI status must fit its real font at %s" % dimensions)
        check(indicator.get_global_rect().end.x <= root.get_visible_rect().size.x,
            "Readable MIDI status must remain inside the viewport at %s" % dimensions)
    # A different installed/theme font must invalidate the intrinsic width,
    # while changing status alone must not make the tempo column jump.
    app.game_input_indicator.add_theme_font_override("font", Design.font(900))
    await process_frame
    await process_frame
    var changed_width: float = app.game_input_indicator.get_theme_font("font").get_string_size(
        "MIDI CONNECTED", HORIZONTAL_ALIGNMENT_LEFT, -1, 13).x
    check(app.game_input_indicator.size.x - 32.0 >= ceilf(changed_width),
        "MIDI status must remeasure when its theme font changes")
    var connected_width: float = app.game_input_indicator.size.x
    app.game_input_indicator.present({"device": "", "preview_only": true})
    await process_frame
    await process_frame
    check(app.game_input_indicator.size.x == connected_width,
        "Disconnect must not shift the tempo column")
    root.size = Vector2i(1024, 768)
    await process_frame
    await process_frame
    check(app.practice_controls.get_child_count() == 3,
        "New gaming cues must not introduce a fourth transport button")
    check(app.score_frame.get_global_rect().end.x <= root.get_visible_rect().size.x + 2.0,
        "The music stage must not overflow a normal laptop viewport")
    print("PHASE79_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
