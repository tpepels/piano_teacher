extends SceneTree

var app: Control
var folder: String
var failures: Array[String] = []

func _initialize() -> void:
    call_deferred("run")

func wait_for(predicate: Callable, seconds: float = 60.0) -> bool:
    var deadline := Time.get_ticks_msec() + int(seconds * 1000.0)
    while not predicate.call():
        if Time.get_ticks_msec() > deadline:
            failures.append("Timed out waiting for UI")
            return false
        await process_frame
    return true

func score_ready() -> bool:
    return app.timeline_preview != null and app._native_score_ready() \
        and app.timeline_preview.is_visible_in_tree() and not app.layout_pending \
        and not app.timeline_model_pending

func api(route: String, body: Dictionary) -> Dictionary:
    var request := HTTPRequest.new()
    root.add_child(request)
    request.request("http://127.0.0.1:8765" + route, ["Content-Type: application/json"],
        HTTPClient.METHOD_POST, JSON.stringify(body))
    var result: Array = await request.request_completed
    request.queue_free()
    if int(result[1]) != 200:
        failures.append("API failed " + route + " " + str(result[1]))
        return {}
    return JSON.parse_string(result[3].get_string_from_utf8())

func press(text: String) -> void:
    for node in app.find_children("*", "Button", true, false):
        if node.text == text and node.is_visible_in_tree():
            node.pressed.emit()
            return
    failures.append("Button not found " + text)

func capture(name: String) -> void:
    # Review settled drawer opacity/position, not its entrance animation.
    await create_timer(0.3).timeout
    await process_frame
    await process_frame
    RenderingServer.force_draw()
    var frame := root.get_texture().get_image()
    frame.save_png(folder + "/" + name + ".png")
    var color: Color = frame.get_pixel(5, 5)
    if color.r > .2 or color.g > .32 or color.b > .28:
        failures.append("Dark background missing on " + name)
    print("UI_FRAME:", name, " ", frame.get_size())

func run() -> void:
    var args := OS.get_cmdline_user_args()
    folder = args[0]
    var source := args[1]
    root.mode = Window.MODE_WINDOWED
    root.size = Vector2i(1536, 960)
    await api("/settings", {"music_dir": source.get_base_dir(), "fullscreen": false})
    app = load("res://main.gd").new()
    app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root.add_child(app)
    await wait_for(func(): return not app.library_info.is_empty())
    await capture("home")
    press("Music")
    await wait_for(func(): return app.current_screen == "library" and not app.library_pending)
    app.library_search.text = source.get_file().get_basename().replace("_", " ")
    app._populate_library()
    await capture("library")
    await api("/library/open", {"id": source.get_file()})
    app._navigate("practice")
    await wait_for(func(): return score_ready())
    await api("/control", {"action": "tempo", "bpm": 80})
    await wait_for(func(): return int(app.last_state.get("bpm", 0)) == 80 and score_ready())
    app.start_button.pressed.emit()
    app._navigate("settings") # The Start HTTP response has not arrived yet.
    await wait_for(func(): return bool(app.last_state.get("paused", false)))
    if app.current_screen != "settings":
        failures.append("Immediate Settings detour must retain its destination")
    app._go_back()
    app.start_button.pressed.emit()
    await wait_for(func(): return app._transport_beat_now() >= .3 and bool(app.last_state.get("running", false)) and not bool(app.last_state.get("paused", true)))
    app.start_button.pressed.emit()
    await wait_for(func(): return bool(app.last_state.get("paused", false)))
    await capture("practice")
    press("Path")
    await wait_for(func(): return not app.lesson_pending and app.lesson_rows.get_child_count() > 0)
    await capture("lesson")
    app._go_back()
    press("Settings")
    await wait_for(func(): return not app.settings_pending)
    app.metronome_toggle.button_pressed = false
    await wait_for(func(): return not app.action_pending and not bool(app.preferences.get("metronome", true)))
    app.tempo_setting.value = 60
    press("Apply tempo")
    await wait_for(func(): return int(app.last_state.get("target_bpm", 0)) == 60 and score_ready())
    app._show_devices()
    await process_frame
    if app.device_menu.get_item_id(0) != -2:
        failures.append("MIDI menu must offer an ungraded timing preview")
    await capture("midi-menu")
    app.device_menu.hide()
    app.device_menu.id_pressed.emit(-2)
    await wait_for(func(): return not app.action_pending and str(app.last_state.get("device", "")) == "")
    for dimensions in [Vector2i(1536,960), Vector2i(1024,768), Vector2i(800,600)]:
        root.size = dimensions
        await capture("settings-%dx%d" % [dimensions.x, dimensions.y])
        app._navigate("practice")
        await capture("practice-%dx%d" % [dimensions.x, dimensions.y])
        var visible_width: float = root.get_visible_rect().size.x
        if app.practice_controls.get_global_rect().end.x > visible_width + 1:
            failures.append("Practice controls overflow " + str(dimensions))
        app._navigate("settings")
    var saved_hand: String = str(app.last_state.get("hand", ""))
    var saved_tempo: int = int(app.last_state.get("target_bpm", 0))
    app.library_search.text = ""
    app._navigate("library")
    await wait_for(func(): return not app.library_pending)
    await capture("library-recent-800x600")
    var continued := false
    for row in app.library_rows.find_children("*", "Button", true, false):
        if str(row.get_meta("library_detail", "")).begins_with("Continue from saved place"):
            row.pressed.emit()
            continued = true
            break
    if not continued:
        failures.append("Music drawer must expose Continue for the imported piece")
    else:
        await wait_for(func(): return not app.action_pending and app.current_screen == "practice" \
            and score_ready())
        if app.open_picker.visible or str(app.last_state.get("hand", "")) != saved_hand \
                or int(app.last_state.get("target_bpm", 0)) != saved_tempo:
            failures.append("Continue must restore saved hand and tempo without a starting-point picker")
        await capture("continued-practice-800x600")
    var file := FileAccess.open(folder + "/ui-result.json", FileAccess.WRITE)
    file.store_string(JSON.stringify({"failures": failures}, "  "))
    print("UI_REVIEW:", "PASS" if failures.is_empty() else str(failures))
    for child in app.get_children():
        if child is Timer:
            child.stop()
    await wait_for(func(): return not app.state_pending and not app.device_pending and not app.library_pending and not app.settings_pending and not app.lesson_pending and not app.action_pending)
    quit(0 if failures.is_empty() else 1)
