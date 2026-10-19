extends SceneTree
# Desktop-only real-pixel diagnostic: same main.gd, HTTP engine, Verovio PNG,
# ScoreStrip, HUD and animation that the pianist actually sees.
# Run under a real Linux display (Xvfb is supported); never with --headless.

var app: Control
var folder: String
var errors: Array[String] = []
var frames: Array = []

func _initialize() -> void:
    call_deferred("_run")

func _wait_until(predicate: Callable, seconds: float, label: String) -> bool:
    var deadline: int = Time.get_ticks_msec() + roundi(seconds * 1000.0)
    while not predicate.call():
        if Time.get_ticks_msec() >= deadline:
            errors.append("Timeout: " + label)
            return false
        await process_frame
    return true

func _api(path: String, payload: Dictionary) -> Dictionary:
    var client := HTTPRequest.new()
    root.add_child(client)
    client.timeout = 35.0
    var request_error := client.request("http://127.0.0.1:8765" + path,
        ["Content-Type: application/json"], HTTPClient.METHOD_POST,
        JSON.stringify(payload))
    if request_error != OK:
        errors.append("API request failed: " + path)
        client.queue_free()
        return {}
    var result: Array = await client.request_completed
    client.queue_free()
    if int(result[1]) != 200:
        errors.append("API status " + str(result[1]) + ": " + path)
        return {}
    var parsed: Variant = JSON.parse_string(result[3].get_string_from_utf8())
    if not parsed is Dictionary:
        errors.append("API invalid JSON: " + path)
        return {}
    return parsed

func _capture(label: String) -> void:
    # Allow the real HUD and notation to settle; do not capture the initial
    # opaque loading panel or a canvas before the raster textures arrive.
    await process_frame
    await process_frame
    RenderingServer.force_draw()
    var image: Image = root.get_texture().get_image()
    var path: String = folder.path_join(label + ".png")
    if image.is_empty() or image.save_png(path) != OK:
        errors.append("Cannot capture real rendered desktop: " + label)
        return
    var bounds: Rect2 = app.score_frame.get_global_rect()
    var rows: Array = app.staff_continuity.staff_lines
    var info := {
        "frame": label, "image_size": [image.get_width(), image.get_height()],
        "score_frame": [bounds.position.x, bounds.position.y,
                        bounds.size.x, bounds.size.y],
        "staff_rows": rows.size(),
        "note_count": app.score_layout.get("notes", []).size(),
        "glyph_tile_count": app.score_tiles.size(),
        "score_width": app.score_content.size.x,
        "current_hand": str(app.last_state.get("hand", "")),
        "transport_phase": str(app.last_state.get("phase", "")),
        "clock_beat": app._transport_beat_now(),
        "fallback": str(app.score_layout.get("strip_timing_fallback", ""))
    }
    frames.append(info)
    if bounds.size.x < float(image.get_width()) * .65 or bounds.size.y < 250:
        errors.append("Practice sheet must dominate the desktop viewport")
    if rows.size() != 10:
        errors.append("Both five-line piano staves must be present: " + str(rows.size()))
    if int(info.note_count) <= 0 or int(info.glyph_tile_count) <= 0:
        errors.append("Real practice notation has no measured notes or tiles")
    print("MIDI_DESKTOP_FRAME:", label, " size=", image.get_size(),
        " notes=", info.note_count, " tiles=", info.glyph_tile_count)

func _notation_ready() -> bool:
    return app.score_view.texture != null and \
        app.rendered_revision == app.revision and \
        not app.score_layout.get("notes", []).is_empty() and \
        app.score_tiles.size() > 0 and \
        app.score_frame.is_visible_in_tree()

func _is_counting() -> bool:
    return str(app.last_state.get("phase", "")) == "count_in" and \
        bool(app.last_state.get("running", false))

func _is_playing() -> bool:
    return str(app.last_state.get("phase", "")) == "playing"

func _run() -> void:
    var args: PackedStringArray = OS.get_cmdline_user_args()
    if args.size() != 1:
        push_error("Usage: -- OUTPUT_DIR")
        quit(2)
        return
    folder = args[0]
    DirAccess.make_dir_recursive_absolute(folder)
    root.mode = Window.MODE_WINDOWED
    root.size = Vector2i(1536, 960)
    app = load("res://main.gd").new()
    app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root.add_child(app)
    await process_frame
    await process_frame
    app._navigate("practice")
    var ready: bool = await _wait_until(
        Callable(self, "_notation_ready"), 100.0, "real notation in practice stage")
    if ready:
        await _capture("ready")
        var started: Dictionary = await _api("/control", {"action": "start"})
        if str(started.get("phase", "")) != "count_in":
            errors.append("Expected MIDI-less count-in from real engine")
        else:
            var counting: bool = await _wait_until(
                Callable(self, "_is_counting"), 8.0, "count-in state")
            if counting:
                await _capture("count-in")
            var playing: bool = await _wait_until(
                Callable(self, "_is_playing"), 16.0, "playing state")
            if playing:
                await create_timer(.25).timeout
                await _capture("playing")
    var file := FileAccess.open(folder.path_join("desktop-report.json"), FileAccess.WRITE)
    if file == null:
        errors.append("Could not save report")
    else:
        file.store_string(JSON.stringify({"frames": frames, "errors": errors}, "  ") + "\n")
        file.close()
    print("MIDI_DESKTOP_FAILURES:", errors.size())
    for issue in errors:
        push_error(issue)
    quit(0 if errors.is_empty() else 1)
