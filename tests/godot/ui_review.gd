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
    await process_frame
    await process_frame
    await RenderingServer.frame_post_draw
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
    press("Browse library  →")
    await wait_for(func(): return app.current_screen == "library" and not app.library_pending)
    app.library_search.text = source.get_file().get_basename().replace("_", " ")
    app._populate_library()
    await capture("library")
    await api("/library/open", {"id": source.get_file()})
    app._navigate("practice")
    await wait_for(func(): return app.score_view.texture != null and app.rendered_revision == app.revision)
    await api("/control", {"action": "tempo", "bpm": 80})
    await wait_for(func(): return int(app.last_state.get("bpm", 0)) == 80 and app.score_view.texture != null)
    app.start_button.pressed.emit()
    await wait_for(func(): return app._transport_beat_now() >= .3 and bool(app.last_state.get("running", false)))
    app.pause_button.pressed.emit()
    await wait_for(func(): return bool(app.last_state.get("paused", false)))
    await capture("practice")
    press("Lesson path")
    await wait_for(func(): return not app.lesson_pending and app.lesson_rows.get_child_count() > 0)
    await capture("lesson")
    press("← Practice")
    press("Settings")
    await wait_for(func(): return not app.settings_pending)
    app.metronome_toggle.button_pressed = false
    await wait_for(func(): return not app.action_pending and not bool(app.preferences.get("metronome", true)))
    app.tempo_setting.value = 60
    press("Apply tempo")
    await wait_for(func(): return int(app.last_state.get("target_bpm", 0)) == 60 and app.score_view.texture != null)
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
    var file := FileAccess.open(folder + "/ui-result.json", FileAccess.WRITE)
    file.store_string(JSON.stringify({"failures": failures}, "  "))
    print("UI_REVIEW:", "PASS" if failures.is_empty() else str(failures))
    quit(0 if failures.is_empty() else 1)
