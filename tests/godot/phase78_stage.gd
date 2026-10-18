extends SceneTree

const Design := preload("res://practice_theme.gd")

# Phase 7.8: real Godot modules, real controller rendering state, no
# synthetic grading. Ambient beat movement must not resemble a note hit.
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
        print("PHASE78_FAIL:", message)

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var Stage = load("res://game_stage.gd")
    var CountIn = load("res://game_countin.gd")
    check(Stage != null and CountIn != null, "Score lighting and count-in must load")
    if Stage == null or CountIn == null:
        quit(1)
        return
    check(Design.STAGE.get_luminance() > .8 and
        Design.SCORE_INK.get_luminance() < .25 and
        Design.FOREST.get_luminance() < .1,
        "Moodboard light score must have dark notation against forest shell")
    var stage = Stage.new()
    root.add_child(stage)
    stage.size = Vector2(1200, 650)
    stage.set_staff_band(.31, .72)
    check(absf(stage.staff_band_top - .31) < .001
        and absf(stage.staff_band_bottom - .72) < .001,
        "Reactive musical light must use real measured staff bounds")
    stage.present({"phase":"playing", "running":true,
        "preview_only":true, "progress":.25})
    stage.sync_beat(-1.25, 3, true)
    check(stage.score_preview and stage.beats_per_bar == 3,
        "Ungraded preview must use neutral meter-synchronized lighting")
    check(absf(stage.beat_fraction - .75) < .0001
        and stage.beat_in_bar == 1,
        "Beats and preparation lead-in use backend musical positions")
    check(stage.impact_energy == 0.0,
        "Preview, ambient meter and onset glows cannot fabricate a note hit")
    stage.sync_beat(1.0, 4, false)
    check(not stage.score_preview and stage.beat_in_bar == 1
        and stage.beats_per_bar == 4,
        "Moving light respects the active musical meter")
    stage.react("on_time")
    check(stage.impact_age == 0.0 and stage.impact_energy > .3
        and stage.impact_tone == Design.MINT,
        "A genuinely graded note triggers visible teal particles")
    stage._process(.2)
    check(stage.impact_age > 0 and stage.impact_energy > 0,
        "One real MIDI event grows and fades a visual burst")
    stage.react("unexpected")
    check(stage.impact_tone == Design.CORAL and stage.impact_age == 0.0,
        "Incorrect physical notes visibly replace the success colour")
    stage.present({"phase":"paused", "running":true, "paused":true})
    var frozen: float = stage.beat_fraction
    stage.sync_beat(2.4, 4, false)
    check(not stage.transport_active and absf(stage.beat_fraction - frozen) < .0001,
        "Pausing must freeze metrical glow along with the actual score clock")
    stage._process(3.0)
    check(stage.impact_energy <= .001, "Effects finish rather than flickering forever")

    var count_in = CountIn.new()
    root.add_child(count_in)
    count_in.size = Vector2(142, 38)
    count_in.present(-3.0, 3, true, false)
    check(count_in.visible and count_in.beats_left == 3 and count_in.current == 0,
        "Three beat lead-in begins with a readable 3 and downbeat")
    count_in.present(-2.0, 3, true, false)
    check(count_in.beats_left == 2 and count_in.current == 1,
        "Countdown decrements on the backend beat, without an internal timer")
    count_in.present(-.01, 3, true, false)
    check(count_in.beats_left == 1,
        "The last preparation beat shows 1 instead of a premature zero")
    count_in.present(0.0, 3, true, false)
    check(not count_in.visible and count_in.beats_left == 0,
        "The countdown disappears exactly at the first playable beat")
    count_in.present(-1.4, 7, true, false)
    check(count_in.count == 7 and count_in.visible,
        "Irregular meter still has a bounded, readable beat display")
    count_in.present(-1.3, 7, true, true)
    check(not count_in.visible, "Pause never shows a moving count-in")

    # Check the stage of the actual Godot UI. It must display a preview
    # without its own tempo clock, and the score must remain the dominant
    # area of the interface at compact laptop dimensions.
    root.mode = Window.MODE_WINDOWED
    root.size = Vector2i(1024, 768)
    var app := FixtureApp.new()
    app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root.add_child(app)
    await process_frame
    await process_frame
    check(app.overlay_drawer.size.x >= 510.0,
        "At 1024px the library must not collapse to a 400px website sidebar")
    var music_row = load("res://library_row.gd").new()
    root.add_child(music_row)
    music_row.set_entry("Chopin - Nocturne", "MIDI - Music folder")
    music_row.set_text_scale(1.3)
    var title_size: int = music_row.title_label.get_theme_font_size("font_size")
    var detail_size: int = music_row.detail_label.get_theme_font_size("font_size")
    check(title_size >= 20 and detail_size >= 14 and title_size > detail_size,
        "Music tiles retain readable title/metadata hierarchy at display scale")
    check(music_row.title_label.get_theme_font("font") != music_row.detail_label.get_theme_font("font"),
        "Music titles use the editorial face while metadata stays in the interface face")
    music_row.queue_free()
    check(app.game_stage.get_parent() == app.score_frame,
        "Beat lighting lives beneath the same score canvas as real engraving")
    check(app.game_count_in.get_parent() == app.score_frame,
        "Countdown stays inside the music rather than creating a website row")
    app._update_visual_frame_rate({"running":false, "paused":false})
    check(Engine.max_fps == 30, "Idle Godot presentation must run at lower CPU cost")
    check(OS.low_processor_usage_mode, "Idle stage must render on demand")
    app._update_visual_frame_rate({"running":true, "paused":false})
    check(Engine.max_fps == 60, "Moving sheet music retains the full 60 FPS budget")
    check(not OS.low_processor_usage_mode, "Moving score requires continuous frames")
    app._update_visual_frame_rate({"running":true, "paused":true})
    check(Engine.max_fps == 30, "Pausing reduces visual CPU usage")
    check(OS.low_processor_usage_mode, "Paused score returns to low CPU mode")
    app.last_state = {"loaded":true, "running":true, "paused":false,
        "phase":"count_in", "mode":"practice", "preview_only":true,
        "clock_beat":-1.5, "bpm":60.0, "count_in_bar_beats":3,
        "transport_id":12}
    app.last_state_tick = Time.get_ticks_msec()
    app.game_stage.present(app.last_state)
    app._process(1.0 / 60.0)
    check(app.game_stage.score_preview and app.game_stage.transport_active,
        "The actual UI samples preview beat lighting from its transport")
    check(app.game_count_in.visible and app.game_count_in.beats_left == 2,
        "The actual UI shows an unobtrusive numeric preparation countdown")
    app.last_state["paused"] = true
    app.game_stage.present(app.last_state)
    app._process(1.0 / 60.0)
    check(not app.game_stage.transport_active and not app.game_count_in.visible,
        "The UI freezes both the score and countdown on pause")
    check(app.practice_controls.get_child_count() == 3,
        "Performance lighting cannot add menus or transport controls")
    print("PHASE78_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
