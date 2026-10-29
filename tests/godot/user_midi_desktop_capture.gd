extends SceneTree
# Desktop-only real-pixel diagnostic: the production native Godot view,
# HTTP engine, authentic Verovio glyphs, HUD and animation the pianist sees.
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
    # opaque loading panel or a canvas before native glyphs and model arrive.
    await process_frame
    await process_frame
    # Sample the same clock used to draw the frame, not one taken after
    # PNG encoding (which may take 20-50ms on a software-rendered CI GPU).
    var capture_beat: float = app.practice_view.stage.renderer.clock_beat
    RenderingServer.force_draw()
    var image: Image = root.get_texture().get_image()
    var path: String = folder.path_join(label + ".png")
    if image.is_empty() or image.save_png(path) != OK:
        errors.append("Cannot capture real rendered desktop: " + label)
        return
    var bounds: Rect2 = app.practice_view.stage.score_frame.get_global_rect()
    var renderer = app.practice_view.stage.renderer
    var rows: Array = []
    if _native_notation_ready():
        var gap: float = renderer.staff_gap()
        for staff in ["right","left"]:
            var middle: float = renderer.layout.staff_center(staff)
            for line in range(-2,3):
                rows.append(middle+float(line)*gap)
    var visible_heads := 0
    var native_bounds := Rect2(Vector2.ZERO, renderer.size)
    for center in renderer.drawn_noteheads.values():
        if native_bounds.has_point(center):
            visible_heads += 1
    var info := {
        "frame": label, "screen": app.current_screen,
        "image_size": [image.get_width(), image.get_height()],
        "score_frame": [bounds.position.x, bounds.position.y,
                        bounds.size.x, bounds.size.y],
        "staff_rows": rows.size(),
        "staff_clefs": app.score_layout.get("staff_clefs", {}),
        "note_count": app.score_layout.get("notes", []).size(),
        "native_noteheads": renderer.drawn_noteheads.size(),
        "visible_noteheads": visible_heads,
        "score_width": renderer.size.x,
        "pixels_per_beat": renderer.timeline.pixels_per_beat,
        "model_notes": renderer.timeline.notes.size(),
        "native_ready": _native_notation_ready(),
        "native_failure": _native_failure(),
        "current_hand": str(app.last_state.get("hand", "")),
        "transport_phase": str(app.last_state.get("phase", "")),
        "clock_beat": capture_beat
    }
    frames.append(info)
    if app.current_screen == "practice":
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
        if int(info.note_count) <= 0 or int(info.model_notes) <= 0 or not bool(info.native_ready):
            errors.append("Real practice notation has no source notes or current native score")
        if str(info.transport_phase) != "count_in" and int(info.visible_noteheads) <= 0:
            errors.append("Native practice view painted no visible source noteheads: " + label)
    if app.current_screen == "lesson":
        var activity_row: Control = app.find_child("LessonActivityRow", true, false)
        var caption: Label = app.find_child("LessonActivityCaption", true, false)
        if activity_row == null or caption == null:
            errors.append("Lesson path Activity controls missing")
        else:
            var activity_rect: Rect2 = activity_row.get_global_rect()
            var caption_rect: Rect2 = caption.get_global_rect()
            var dropdown_rect: Rect2 = app.lesson_view.mode_choice.get_global_rect()
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
            if not app.lesson_view.rows.is_visible_in_tree():
                errors.append("Lesson step list is not visible at " + label)
    print("MIDI_DESKTOP_FRAME:", label, " size=", image.get_size(),
        " notes=", info.note_count, " native_heads=", info.native_noteheads)

func _lesson_ready() -> bool:
    return not app.lesson_session.pending and app.lesson_view.rows.get_child_count() > 0 \
        and app.current_screen == "lesson" and app.lesson_view.summary.text.contains("stages completed")


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
    if app.practice_view.stage.renderer == null:
        return ""
    return str(app.practice_view.stage.renderer.get("failure_reason"))


func _native_notation_ready() -> bool:
    return app.practice_view.stage.renderer != null and app._native_score_ready() and \
        app.practice_view.stage.renderer.is_visible_in_tree() and not app.layout_pending and \
        not app.timeline_model_pending


func _notation_ready() -> bool:
    return _native_notation_ready() and \
        not app.practice_view.stage.renderer.timeline.notes.is_empty() and \
        not app.score_layout.get("notes", []).is_empty() and \
        app.practice_view.stage.score_frame.is_visible_in_tree()

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
    if not ready:
        errors.append("Native semantic renderer unavailable: " + _native_failure())
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
