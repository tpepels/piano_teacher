extends SceneTree

# Exercise the actual interface and handlers without a backend or MIDI device.
# Only outbound HTTP requests are replaced; controls and navigation stay real.
class FixtureApp extends "res://main.gd":
    var commands: Array[Dictionary] = []

    func _ready() -> void:
        _build_interface()
        resized.connect(_update_responsive_layout)
        _update_responsive_layout()
        set_process(false)

    func _send_action(command: Dictionary) -> void:
        commands.append(command.duplicate(true))

    func _request_library() -> void:
        pass

    func _request_settings() -> void:
        pass

    func _request_devices() -> void:
        pass

    func _request_lesson() -> void:
        pass

    func _request_layout() -> void:
        pass

var failures: Array[String] = []
var app: FixtureApp

func _initialize() -> void:
    call_deferred("run")

func check(ok: bool, message: String) -> void:
    if not ok:
        failures.append(message)
        print("INTERACTION_FAIL:", message)

func state(phase: String = "ready") -> Dictionary:
    return {
        "loaded": true, "title": "A long piece title that should leave room for the tempo",
        "kind": "learn", "first_bar": 1, "last_bar": 6,
        "exercise": 1, "exercise_count": 60,
        "lesson_level": "skeleton", "lesson_level_number": 1,
        "lesson_level_count": 2, "required_notes": 11,
        "lesson_step": 1, "lesson_steps": 301, "lesson_steps_mastered": 0,
        "hand": "right", "hands": ["right", "left", "both"],
        "bpm": 80, "original_bpm": 100, "target_bpm": 80,
        "streak": 0, "mastered": 0, "phase": phase,
        "countdown": 1.0 if phase == "count_in" else 0.0,
        "lead_in_bars": 1, "play_from_beat": 0.0, "recovery_beat": null,
        "clock_beat": -1.0 if phase == "count_in" else 2.0,
        "paused": phase == "paused", "transport_id": 7,
        "awaiting_score_revision": null, "count_in_beats": 3,
        "count_in_bar_beats": 3, "count_in_meter": [3, 4],
        "midi_notes": 0, "preview_only": true,
        "progress": 0.1, "duration": 9.0, "beat": 2.0,
        "duration_beats": 12.0, "running": phase in ["count_in", "playing", "paused"],
        "device": "", "feedback": "MIDI piano disconnected. Connect your USB piano in Settings, or start a timing preview to read along. Your place will be kept while you check the connection.",
        "revision": 1, "feedback_marks": [], "feedback_unmapped": 0,
        "midi_input_count": 0, "midi_input_note": null, "midi_input_age": null,
        "metronome": true,
    }

func show_state(phase: String = "ready") -> void:
    app._on_state(0, 200, PackedStringArray(), JSON.stringify(state(phase)).to_utf8_buffer())

func key(code: Key) -> void:
    var event := InputEventKey.new()
    event.keycode = code
    event.pressed = true
    app._unhandled_key_input(event)

func visible_buttons(prefix: String) -> Array[Button]:
    var buttons: Array[Button] = []
    for node in app.find_children("*", "Button", true, false):
        if node.is_visible_in_tree() and node.text.begins_with(prefix):
            buttons.append(node)
    return buttons

func expect_command(action: String, description: String) -> void:
    check(app.commands == [{"action": action}], description + ": " + str(app.commands))
    app.commands.clear()

func test_primary_transport() -> void:
    show_state()
    app.start_button.pressed.emit()
    expect_command("start", "Primary button starts a ready passage")
    for phase in ["count_in", "playing", "feedback", "recovering", "loading"]:
        show_state(phase)
        app.commands.clear() # Ignore the ordinary loading score-ready acknowledgement.
        key(KEY_SPACE)
        expect_command("pause", "Space pauses " + phase + " without abandoning the attempt")
        check(app.start_button.text.begins_with("Pause"), "Primary control offers Pause during " + phase)
        check(visible_buttons("Pause").size() == 1, "Only one Pause control is visible during " + phase)
        app.start_button.pressed.emit()
        expect_command("pause", "Primary button pauses " + phase)
    show_state("paused")
    key(KEY_SPACE)
    expect_command("resume", "Space resumes the same paused attempt")
    app.start_button.pressed.emit()
    expect_command("resume", "Primary button resumes the same paused attempt")
    check(visible_buttons("Resume").size() == 1, "Paused practice offers exactly one Resume control")

func test_secondary_stop() -> void:
    show_state()
    var ready_stops := visible_buttons("Stop")
    check(ready_stops.is_empty() or ready_stops[0].disabled, "Stop is unavailable before an attempt starts")
    for phase in ["count_in", "playing", "paused", "feedback", "recovering", "loading"]:
        show_state(phase)
        app.commands.clear()
        var stops := visible_buttons("Stop")
        check(stops.size() == 1, "An active attempt has one explicit secondary Stop control: " + phase)
        if stops.size() == 1:
            check(stops[0] != app.start_button, "Stop never replaces the primary Pause/Resume control")
            check(not stops[0].disabled, "Stop remains available during " + phase)
            stops[0].pressed.emit()
            expect_command("stop", "Secondary Stop abandons " + phase)

func routed_key(code: Key, unicode_value: int = 0) -> void:
    # Send both halves through the whole window: a focused Button can activate
    # on release after a shortcut has already handled the press.
    for pressed in [true, false]:
        var event := InputEventKey.new()
        event.keycode = code
        event.unicode = unicode_value
        event.pressed = pressed
        Input.parse_input_event(event)
        await process_frame

func test_focused_shortcuts() -> void:
    for phase in ["ready", "playing", "paused"]:
        show_state(phase)
        for control in app.practice_controls.get_children():
            if not control is Button or control.disabled:
                continue
            control.grab_focus()
            await process_frame
            check(root.gui_get_focus_owner() == control, "Transport control receives actual keyboard focus")
            app.commands.clear()
            await routed_key(KEY_SPACE)
            var action := "start" if phase == "ready" else "pause" if phase == "playing" else "resume"
            expect_command(action, "Space performs one transport action with " + control.text + " focused during " + phase)
    # Enter keeps ordinary button activation, and typing in Settings remains
    # native text input rather than invoking practice shortcuts.
    show_state()
    for control in app.practice_controls.get_children():
        if control is Button and control.text == "Next →":
            control.grab_focus()
    await routed_key(KEY_ENTER)
    expect_command("next", "Enter activates the focused button")
    app._navigate("settings")
    app.folder_edit.text = ""
    app.folder_edit.grab_focus()
    await routed_key(KEY_R, 114)
    await routed_key(KEY_SPACE, 32)
    check(app.folder_edit.text == "r ", "Settings fields retain normal text and Space input")
    check(app.commands.is_empty(), "Typing in Settings never invokes practice shortcuts")

func test_practice_detours() -> void:
    for destination in ["settings", "lesson"]:
        for phase in ["count_in", "playing", "feedback", "recovering", "loading"]:
            app._navigate("practice")
            show_state(phase)
            app.commands.clear()
            app._navigate(destination)
            expect_command("pause", "Opening " + destination + " pauses " + phase)
            show_state("paused") # The backend has acknowledged the pause.
            var beat: float = app.last_state.clock_beat
            var transport: int = app.last_state.transport_id
            check(app.has_method("_go_back"), "Detours provide one Back action that remembers their origin")
            if app.has_method("_go_back"):
                app.call("_go_back")
                check(app.current_screen == "practice", "Back from " + destination + " returns to practice")
                check(app.commands.is_empty(), "Back leaves the same attempt paused until the user resumes")
                check(app.last_state.clock_beat == beat and app.last_state.transport_id == transport,
                    "Back preserves the paused beat and attempt")
        app._navigate("practice")
        show_state("paused")
        app.commands.clear()
        app._navigate(destination)
        check(app.commands.is_empty(), "An already paused attempt is not stopped when opening " + destination)

func test_settings_back_origin() -> void:
    for origin in ["home", "library"]:
        app._navigate(origin)
        show_state() # A score can remain loaded while browsing the library.
        app.commands.clear()
        app._navigate("settings")
        check(app.has_method("_go_back"), "Settings Back must remember where Settings was opened")
        if app.has_method("_go_back"):
            app.call("_go_back")
            check(app.current_screen == origin, "Settings returns to " + origin + " even when a score is loaded")
            check(app.commands.is_empty(), "Browsing Settings does not alter the stopped passage")

func test_abandon_practice() -> void:
    for destination in ["home", "library"]:
        for phase in ["count_in", "playing", "paused", "feedback", "recovering", "loading"]:
            app._navigate("practice")
            show_state(phase)
            app.commands.clear()
            app._navigate(destination)
            expect_command("stop", "Leaving practice for " + destination + " abandons " + phase)

func test_compact_feedback() -> void:
    show_state()
    await process_frame
    await process_frame
    var viewport := root.get_visible_rect()
    check(app.feedback_label.get_line_count() > 1,
        "MIDI connection guidance wraps into readable lines at 800 pixels")
    var font_size: int = app.feedback_label.get_theme_font_size("font_size")
    check(app.feedback_label.size.y >= app.feedback_label.get_line_count() * font_size,
        "Feedback reserves enough height for every wrapped line")
    for control in [app.feedback_label, app.progress_label, app.practice_controls, app.speed_label]:
        check(viewport.encloses(control.get_global_rect()), "Compact practice control remains inside the viewport: " + str(control))

func test_instructional_transition() -> void:
    var retry: Dictionary = state("recovering")
    retry["next_action"] = "Retry measures 3–4 at 72 BPM"
    retry["transition_in_seconds"] = 1.5
    app._on_state(0,200,PackedStringArray(),JSON.stringify(retry).to_utf8_buffer())
    check(app.lesson_info_label.text.contains("Retry measures 3–4 at 72 BPM"),
        "The teaching instruction says exactly what will happen next")
    check(app.lesson_info_label.text.contains("1.5"), "The brief automatic break has a visible countdown")
    retry["phase"] = "paused"
    retry["paused"] = true
    retry["pause_context"] = "recovering"
    app.score_view.texture = null # Pausing loading must not disable Resume.
    app._on_state(0,200,PackedStringArray(),JSON.stringify(retry).to_utf8_buffer())
    check(not app.start_button.disabled, "Resume remains available while the next score is loading")
    check(not app.stop_button.disabled, "Stop remains available during an automatic break")
    retry["mode"] = "learn"
    retry["phase"] = "loading"
    retry["paused"] = false
    app._on_state(0,200,PackedStringArray(),JSON.stringify(retry).to_utf8_buffer())
    app.commands.clear()
    app._toggle_playing()
    check(app.start_button.text.contains("Pause"), "Guided preparation offers Pause")
    check(app.commands.back().get("action") == "pause", "Primary transport pauses guided preparation")

func run() -> void:
    root.mode = Window.MODE_WINDOWED
    root.size = Vector2i(800, 600)
    app = FixtureApp.new()
    app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root.add_child(app)
    await process_frame
    await process_frame
    app._navigate("practice")
    app.revision = 1
    app.layout_revision = 1
    app.rendered_revision = 1
    var image := Image.create(2, 2, false, Image.FORMAT_RGBA8)
    image.fill(Color.WHITE)
    app.score_view.texture = ImageTexture.create_from_image(image)
    var scenario := OS.get_cmdline_user_args()[0]
    match scenario:
        "primary_transport": test_primary_transport()
        "secondary_stop": test_secondary_stop()
        "focused_shortcuts": await test_focused_shortcuts()
        "practice_detours": test_practice_detours()
        "settings_back_origin": test_settings_back_origin()
        "abandon_practice": test_abandon_practice()
        "compact_feedback": await test_compact_feedback()
        "instructional_transition": test_instructional_transition()
        _: check(false, "Unknown interaction scenario: " + scenario)
    print("PRACTICE_INTERACTION_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
