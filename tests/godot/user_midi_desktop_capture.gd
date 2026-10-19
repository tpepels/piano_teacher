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
    # Sample the same clock used to draw the frame, not one taken after
    # PNG encoding (which may take 20-50ms on a software-rendered CI GPU).
    app._layout_moving_score()
    var capture_beat: float = app._transport_beat_now()
    RenderingServer.force_draw()
    var image: Image = root.get_texture().get_image()
    var path: String = folder.path_join(label + ".png")
    if image.is_empty() or image.save_png(path) != OK:
        errors.append("Cannot capture real rendered desktop: " + label)
        return
    var bounds: Rect2 = app.score_frame.get_global_rect()
    var rows: Array = app.staff_continuity.staff_lines
    var info := {
        "frame": label, "screen": app.current_screen,
        "image_size": [image.get_width(), image.get_height()],
        "score_frame": [bounds.position.x, bounds.position.y,
                        bounds.size.x, bounds.size.y],
        "staff_rows": rows.size(),
        "staff_clefs": app.score_layout.get("staff_clefs", {}),
        "note_count": app.score_layout.get("notes", []).size(),
        "glyph_tile_count": app.score_tiles.size(),
        "score_width": app.score_content.size.x,
        "beat_camera": load("res://score_beat_camera.gd").prepare(app.score_layout),
        "exact_ink_grid": bool(app.score_layout.get("exact_ink_grid", false)),
        "native_ready": _native_notation_ready() if
            OS.get_environment("PIANO_TEACHER_NATIVE_NOTATION") == "1" else false,
        "native_failure": _native_failure(),
        "exact_ink_grid_reason": str(app.score_layout.get("exact_ink_grid_reason", "")),
        "current_hand": str(app.last_state.get("hand", "")),
        "transport_phase": str(app.last_state.get("phase", "")),
        "clock_beat": capture_beat,
        "fallback": str(app.score_layout.get("strip_timing_fallback", ""))
    }
    frames.append(info)
    if app.current_screen == "practice":
        var camera_result: Dictionary = info["beat_camera"]
        if bool(camera_result.get("enabled", false)) and \
                float(camera_result.get("max_error_px", INF)) > 2.0:
            errors.append("Unaligned real Verovio notes bypassed the exact-grid guard at " + label)
        if bounds.size.x < float(image.get_width()) * .65 or bounds.size.y < 130:
            errors.append("Practice sheet must dominate the desktop viewport")
        if rows.size() != 10:
            errors.append("Both five-line piano staves must be present: " + str(rows.size()))
        if folder.get_file().begins_with("ala-"):
            var clefs: Dictionary = app.score_layout.get("staff_clefs", {})
            var right: Dictionary = clefs.get("right", {})
            var left: Dictionary = clefs.get("left", {})
            if str(right.get("sign", "")) != "G" or str(left.get("sign", "")) != "F":
                errors.append("Ala piano grand staff requires G clef over F clef")
        if int(info.note_count) <= 0 or int(info.glyph_tile_count) <= 0:
            errors.append("Real practice notation has no measured notes or tiles")
    if app.current_screen == "lesson":
        var activity_row: Control = app.find_child("LessonActivityRow", true, false)
        var caption: Label = app.find_child("LessonActivityCaption", true, false)
        if activity_row == null or caption == null:
            errors.append("Lesson path Activity controls missing")
        else:
            var activity_rect: Rect2 = activity_row.get_global_rect()
            var caption_rect: Rect2 = caption.get_global_rect()
            var dropdown_rect: Rect2 = app.mode_choice.get_global_rect()
            info["activity_rect"] = [
                activity_rect.position.x, activity_rect.position.y,
                activity_rect.size.x, activity_rect.size.y]
            info["caption_rect"] = [
                caption_rect.position.x, caption_rect.position.y,
                caption_rect.size.x, caption_rect.size.y]
            info["selector_rect"] = [
                dropdown_rect.position.x, dropdown_rect.position.y,
                dropdown_rect.size.x, dropdown_rect.size.y]
            if caption_rect.size.x < 80 or caption_rect.size.y > 50:
                errors.append("Activity label wrapped letter-by-letter at " + label)
            if activity_rect.size.y > 70 or dropdown_rect.size.y > 70:
                errors.append("Lesson Activity selector grew vertically at " + label)
            if dropdown_rect.position.x + dropdown_rect.size.x > image.get_width() - 10:
                errors.append("Lesson mode choice overflows viewport at " + label)
            if not app.lesson_rows.is_visible_in_tree():
                errors.append("Lesson step list is not visible at " + label)
    print("MIDI_DESKTOP_FRAME:", label, " size=", image.get_size(),
        " notes=", info.note_count, " tiles=", info.glyph_tile_count)

func _lesson_ready() -> bool:
    return not app.lesson_pending and app.lesson_rows.get_child_count() > 0 \
        and app.current_screen == "lesson" and app.lesson_summary.text.contains("stages completed")


func _settings_ready() -> bool:
    return app.current_screen == "settings" and not app.settings_pending


func _library_ready() -> bool:
    return app.current_screen == "library" and not app.library_pending


func _audit_all_screens() -> void:
    # On the first real MIDI piece, cover desktop, laptop and compact windows.
    # The remaining real MIDI files still cover every main screen at 1536x960.
    var widths: Array[Vector2i] = [Vector2i(1536, 960)]
    if folder.get_file().begins_with("ala-"):
        widths.append(Vector2i(1024, 768))
        widths.append(Vector2i(800, 600))
    for resolution in widths:
        root.size = resolution
        await create_timer(.12).timeout
        var suffix: String = "%dx%d" % [resolution.x, resolution.y]
        app._navigate("lesson")
        if await _wait_until(Callable(self, "_lesson_ready"), 18.0, "lesson " + suffix):
            await _capture("lesson-" + suffix)
        app._navigate("settings")
        if await _wait_until(Callable(self, "_settings_ready"), 12.0, "settings " + suffix):
            await _capture("settings-" + suffix)
        app._navigate("library")
        if await _wait_until(Callable(self, "_library_ready"), 12.0, "library " + suffix):
            await _capture("library-" + suffix)
        app._navigate("practice")
        if await _wait_until(Callable(self, "_notation_ready"), 20.0, "practice " + suffix):
            await _capture("practice-" + suffix)
    root.size = Vector2i(1536, 960)
    await create_timer(.12).timeout
    app._navigate("practice")


func _native_failure() -> String:
    if OS.get_environment("PIANO_TEACHER_NATIVE_NOTATION") != "1" or \
            app.timeline_preview == null:
        return ""
    return str(app.timeline_preview.get("failure_reason"))


func _native_notation_ready() -> bool:
    return app.timeline_preview != null and \
        bool(app.timeline_preview.get("native_ready")) and \
        app.timeline_preview.visible and \
        app.timeline_model_revision == app.revision


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
    if ready and OS.get_environment("PIANO_TEACHER_NATIVE_NOTATION") == "1":
        ready = await _wait_until(Callable(self, "_native_notation_ready"),
            55.0, "pure Godot notation ready")
        if not ready:
            errors.append("Native semantic renderer unavailable: " + str(
                app.timeline_preview.get("failure_reason") if
                app.timeline_preview != null else "missing timeline"))
    if ready:
        await _capture("ready")
        await _audit_all_screens()
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
