extends SceneTree
# A real learner uses the ordinary main scene, HTTP polling and visible controls.
# Python supplies MIDI only through the selected physical-input test adapter.

const Design := preload("res://practice_theme.gd")
var app: Control
var folder := ""
var failures: Array[String] = []
var frames: Array = []
var tracked_id := ""

func _initialize() -> void:
    call_deferred("run")

func check(ok: bool, description: String) -> void:
    if not ok:
        failures.append(description)
        print("TEACHING_FAIL:", description)

func wait_for(predicate: Callable, description: String, seconds: float = 20.0) -> bool:
    var deadline := Time.get_ticks_msec() + int(seconds * 1000)
    while not predicate.call():
        if Time.get_ticks_msec() >= deadline:
            check(false, "Timed out: " + description)
            return false
        await process_frame
    return true

func imported_row() -> Button:
    for row in app.library_rows.find_children("*", "Button", true, false):
        if row is Button and str(row.get_meta("library_title", "")).begins_with("Imported"):
            return row
    return null

func press(text: String) -> void:
    for button in app.find_children("*", "Button", true, false):
        if text == "Practice" and app.current_screen != "practice" and not app.navigation_rail.is_ancestor_of(button):
            continue
        if button.text == text and button.is_visible_in_tree() and not button.disabled:
            button.pressed.emit()
            return
    check(false, "Visible enabled control missing: " + text)

func score_ready() -> bool:
    return app.score_view.texture != null and app.layout_revision == app.revision \
        and app.rendered_revision == app.revision and not app.layout_pending and not app.score_pending

func note_position() -> Vector2:
    for note in app.score_layout.get("notes", []):
        if str(note.get("id", "")) == tracked_id:
            var local: Vector2 = (Vector2(float(note.x), float(note.y)) - app.score_crop_origin) \
                / app.score_crop_size * app.score_content.size
            return app.score_content.get_global_transform_with_canvas() * local
    check(false, "Tracked engraved note missing")
    return Vector2.ZERO

func capture(label: String) -> Dictionary:
    await process_frame
    RenderingServer.force_draw()
    var picture := root.get_texture().get_image()
    var filename := label + ".png"
    check(picture.save_png(folder + "/" + filename) == OK, "Save rendered " + filename)
    var pixel_scale := Vector2(picture.get_size()) / root.get_visible_rect().size
    var entry := {"frame": filename, "phase": app.last_state.get("phase", ""),
        "mode": app.last_state.get("mode", ""), "beat": app._transport_beat_now(),
        "width": picture.get_width(), "height": picture.get_height(),
        "score_height": app.score_frame.size.y}
    var background := picture.get_pixel(5,5)
    check(background.r < .2 and background.g < .32 and background.b < .28,
        "Low-glare dark background: " + label)
    if not tracked_id.is_empty():
        var position := note_position() * pixel_scale
        entry["note_x"] = position.x
        entry["note_y"] = position.y
        # Multiple high-contrast pixels around the source notehead prove this is
        # actual engraving, rather than an empty scene with changing coordinates.
        var ink := 0
        for y in range(int(position.y)-7, int(position.y)+8):
            for x in range(int(position.x)+1, int(position.x)+25):
                if x >= 0 and y >= 0 and x < picture.get_width() and y < picture.get_height():
                    var color := picture.get_pixel(x,y)
                    if color.r > .5 and color.g > .5 and color.b > .45:
                        ink += 1
        entry["notehead_ink"] = ink
        check(ink >= 8 or (str(app.last_state.get("phase", "")) == "count_in" and position.x > app.score_frame.get_global_rect().end.x), "Real notehead pixels remain visible or approach from beyond the count-in: " + label)
    if label == "wrong-note-hint":
        var keyboard: Control = app.hint_keyboard
        check(keyboard.is_visible_in_tree(), "Wrong input reveals contextual keyboard")
        check(keyboard.get_global_rect().end.y <= root.get_visible_rect().size.y,
            "Hint keyboard fits actual desktop viewport")
        check(app.score_frame.size.y >= 135, "Hints preserve readable notation height")
        var expected: Array = app.last_state.teaching.expected_notes
        var painted := 0
        for note in expected:
            var pitch := int(note.pitch)
            check(keyboard._keys.has(pitch), "Expected MIDI pitch has a real key")
            if keyboard._keys.has(pitch):
                var key: Dictionary = keyboard._keys[pitch]
                check(bool(key.expected), "Expected MIDI pitch is highlighted")
                check(keyboard._expected_label.text.contains(str(note.label)),
                    "Visible hint labels exact expected pitch and octave")
                var rect: Rect2 = key.rect
                var local := rect.position + Vector2(rect.size.x * .25, rect.size.y * .75)
                var point: Vector2 = (keyboard.get_global_transform_with_canvas() * local) * pixel_scale
                var color := picture.get_pixelv(Vector2i(point))
                if color.is_equal_approx(Design.SAGE) or color.is_equal_approx(Design.SAGE.darkened(.18)):
                    painted += 1
        check(painted == expected.size(), "Rendered expected keys have the real sage fill")
        check(keyboard._heard_label.text.contains("C#4"), "Wrong heard pitch is shown separately")
        entry["painted_expected_keys"] = painted
        entry["hint_bounds"] = str(keyboard.get_global_rect())
    if app.current_screen == "practice":
        var viewport := root.get_visible_rect()
        for control in [app.start_button, app.practice_retry_button, app.listen_button]:
            check(control.is_visible_in_tree(), "Practice control is visible: " + label)
            check(viewport.encloses(control.get_global_rect()), "Practice control fits viewport: " + label)
    frames.append(entry)
    print("TEACHING_FRAME:", label)
    return entry

func run() -> void:
    var args := OS.get_cmdline_user_args()
    folder = args[0]
    var music := args[1]
    check(DisplayServer.get_name() != "headless", "Real desktop renderer required")
    root.mode = Window.MODE_WINDOWED
    root.size = Vector2i(int(args[2]), int(args[3])) if args.size() >= 4 else Vector2i(1536,960)
    app = load("res://main.gd").new()
    app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root.add_child(app)
    await wait_for(func(): return not app.preferences.is_empty(), "normal initial settings")
    press("Settings")
    await wait_for(func(): return app.current_screen == "settings" and not app.settings_pending,
        "normal Settings screen")
    app.folder_edit.text = music
    press("Save folder")
    await wait_for(func(): return not app.action_pending and str(app.preferences.get("music_dir", "")) == music,
        "user folder saved")
    press("Choose USB MIDI piano")
    await wait_for(func(): return not app.device_pending and app.device_names.has("Journey test piano"),
        "physical input adapter listed")
    app.device_menu.id_pressed.emit(app.device_names.find("Journey test piano"))
    app.device_menu.hide()
    await wait_for(func(): return not app.action_pending and str(app.last_state.get("device", "")) == "Journey test piano",
        "normal UI MIDI selection")
    press("Library")
    await wait_for(func(): return app.current_screen == "library" and not app.library_pending \
        and imported_row() != null, "imported file in normal library")
    var piece_button := imported_row()
    check(piece_button != null and str(piece_button.get_meta("library_title", "")).contains("Imported repeated chords"),
        "User MIDI is the imported library piece")
    piece_button.pressed.emit()
    await wait_for(func(): return app.open_picker.visible, "starting-point dialog opens")
    app.open_mode.select(0)
    press("Open music")
    await wait_for(func(): return app.current_screen == "practice" and score_ready() \
        and str(app.last_state.get("phase", "")) == "guided_wait", "import automatically enters Learn")
    press("Path")
    await wait_for(func(): return app.current_screen == "lesson" and not app.lesson_pending, "hand selection")
    press("Both hands")
    await wait_for(func(): return app.current_screen == "practice" and score_ready() \
        and str(app.last_state.get("hand", "")) == "both" \
        and str(app.last_state.get("phase", "")) == "guided_wait", "generated both-hand fragment")
    tracked_id = str(app.score_layout.notes[0].id)
    check(not app.hint_keyboard.visible, "Successful learner starts without immediate hints")
    var position := note_position()
    await create_timer(.35).timeout
    check(position.distance_to(note_position()) < .1, "Untimed score does not advance with wall clock")
    await capture("guided-ready")
    print("TEACHING_STAGE:wrong-ready")
    await wait_for(func(): return app.hint_keyboard.is_visible_in_tree() \
        and bool(app.last_state.teaching.get("hint_visible", false)), "wrong-note hint arrives through HTTP")
    # Feedback may cover the tiny current notehead at compact display scales.
    # Track the next engraved attack so the pixel check still proves notation
    # survives the keyboard expansion independently of the feedback marker.
    var target_beat := float(app.last_state.teaching.expected_notes[0].beat)
    for note in app.score_layout.notes:
        if float(note.beat) > target_beat + .01:
            tracked_id = str(note.id)
            break
    await capture("wrong-note-hint")
    print("TEACHING_STAGE:hint-rendered")
    await wait_for(func(): return str(app.last_state.get("phase", "")) == "guided_complete",
        "slow fresh MIDI chords finish guided fragment")
    check(not app.hint_keyboard.visible, "Completed fragment hides hint keyboard")
    check(int(app.last_state.get("streak", -1)) == 0 and int(app.last_state.get("mastered", -1)) == 0,
        "Assisted Learn never earns clean mastery")
    tracked_id = str(app.score_layout.notes[-1].id)
    await capture("guided-complete")
    check(app.start_button.text.begins_with("Try rhythm"), "Completion offers Try rhythm")
    app.start_button.pressed.emit()
    await wait_for(func(): return score_ready() and str(app.last_state.get("mode", "")) == "practice" \
        and str(app.last_state.get("phase", "")) == "count_in", "Try rhythm waits for real engraved score then counts in")
    tracked_id = str(app.score_layout.notes[0].id)
    var lead := await capture("practice-count-in")
    await wait_for(func(): return str(app.last_state.get("phase", "")) == "playing" \
        and app._transport_beat_now() >= .15, "real musical time starts")
    var playing := await capture("practice-playing-a")
    check(float(playing.note_x) < float(lead.note_x)-10, "Score approaches line during count-in")
    print("TEACHING_STAGE:practice-playing")
    await create_timer(.5).timeout
    var later := await capture("practice-playing-b")
    check(float(later.note_x) < float(playing.note_x)-10, "Actual notes move left during practice")
    check(not app.hint_keyboard.visible or app.hint_keyboard._live_mode,
        "Timed practice switches from the guided target to real live MIDI input")
    app.stop_button.pressed.emit()
    await wait_for(func(): return not app.action_pending and not bool(app.last_state.get("running", true)) \
        and str(app.last_state.get("phase", "")) == "ready", "visible Stop abandons practice")
    await capture("stopped")
    var file := FileAccess.open(folder + "/result.json", FileAccess.WRITE)
    file.store_string(JSON.stringify({"failures":failures, "frames":frames,
        "renderer":DisplayServer.get_name()}, "  "))
    # Let the ordinary in-flight requests finish before the desktop closes.
    # Otherwise shutdown itself can sever a valid backend response.
    for child in app.get_children():
        if child is Timer:
            child.stop()
    await wait_for(func(): return not app.state_pending and not app.device_pending \
        and not app.library_pending and not app.settings_pending and not app.lesson_pending \
        and not app.action_pending and not app.layout_pending and not app.score_pending,
        "drain ordinary HTTP requests before exit")
    print("TEACHING_RESULT:", "PASS" if failures.is_empty() else "FAIL")
    quit(0 if failures.is_empty() else 1)
