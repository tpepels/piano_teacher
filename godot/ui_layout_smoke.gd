extends SceneTree

# Actual Godot container geometry smoke, without a backend or piano.
# Re-run at 1536x960, 1024x768 and 800x600. Reject clipped transport
# buttons and pause panels rather than relying on Python unit tests.
class FixtureApp extends "res://main.gd":
    func _ready() -> void:
        # Exercise real widgets/layout without starting HTTP requests or
        # timers that can replace synthetic entries with a live library.
        _build_interface()
        resized.connect(_update_responsive_layout)
        _update_responsive_layout()
        set_process(false)

var failures: Array[String] = []


func _initialize() -> void:
    _run.call_deferred()


func _check(condition: bool, message: String) -> void:
    if not condition:
        failures.append(message)


func _in_viewport(control: Control, viewport: Vector2) -> bool:
    var rect := control.get_global_rect()
    return rect.position.x >= -2.0 and rect.position.y >= -2.0 \
        and rect.end.x <= viewport.x + 2.0 and rect.end.y <= viewport.y + 2.0


func _check_actions(container: Control, viewport: Vector2, label: String) -> void:
    for child in container.get_children():
        if not child is Control or not child.visible:
            continue
        var control := child as Control
        _check(_in_viewport(control, viewport), "%s: %s is outside window" % [label, control.name])
        if control is Button:
            _check(control.size.x + 1.0 >= control.get_combined_minimum_size().x,
                "%s: %s has clipped button width" % [label, control.text])


func _library_entries(rows: Control) -> Array[Button]:
    var entries: Array[Button] = []
    for child in rows.find_children("*", "Button", true, false):
        if child.has_meta("library_title"):
            entries.append(child as Button)
    return entries


func _run() -> void:
    # Godot --headless --script creates a 64x64 root Window even when
    # --resolution is supplied. Explicitly size it before loading the UI.
    var dimensions: PackedStringArray = OS.get_cmdline_user_args()
    var requested: PackedStringArray = (
        dimensions[0].split("x") if not dimensions.is_empty()
        else PackedStringArray(["1536", "960"]))
    if requested.size() != 2:
        push_error("Pass the viewport size as 1536x960")
        quit(2)
        return
    root.size = Vector2i(int(requested[0]), int(requested[1]))
    var scene := FixtureApp.new()
    scene.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root.add_child(scene)
    await process_frame
    scene.call("_navigate", "practice")
    await process_frame
    await process_frame
    var viewport: Vector2 = root.get_visible_rect().size
    _check(str(scene.get("current_screen")) == "practice",
        "Phase 7.1 must open directly on the practice stage")
    _check(not (scene.get("overlay_root") as Control).visible,
        "No drawer is open at startup")
    var browse_button: Button = scene.get("score_browse_button")
    _check(browse_button.visible,
        "Empty practice stage must have a prominent Choose music action")
    var toolbar: Control = scene.get("practice_navigation")
    var transport: Control = scene.get("practice_controls")
    var score: Control = scene.get("score_frame")
    print("PHASE2_LAYOUT_DIAGNOSTIC: window=", viewport, " scene=", scene.size,
        " toolbar=", toolbar.get_global_rect(), " transport=", transport.get_global_rect(),
        " score=", score.get_global_rect())
    _check_actions(toolbar, viewport, "Toolbar")
    _check_actions(transport, viewport, "Transport")
    _check(score.size.y >= 135.0, "Notation area became unusably small")
    # A sourced MIDI piece must open in a true centered in-app modal, not
    # a narrow embedded Window accidentally stretched to viewport height.
    scene.call("_show_open_picker", {"title": "Ala_-_Joep_Beving",
        "piece_last_bar": 77, "selected_start_bar": 1})
    await process_frame
    await process_frame
    var preview_picker: Control = scene.get("open_picker")
    var modal: PanelContainer = scene.get("open_picker").get("panel")
    _check(preview_picker.visible and not scene.get("overlay_root").visible,
        "Starting point must hide the library drawer behind its modal")
    _check(modal.size.x >= minf(500.0, viewport.x - 36.0) and
        modal.size.y < viewport.y * .90,
        "Starting point must be broad and compact, not a tall thin window")
    _check(absf(modal.get_global_rect().get_center().x - viewport.x * .5) < 6.0 and
        absf(modal.get_global_rect().get_center().y - viewport.y * .5) < 6.0,
        "Starting point modal must be centered in the real viewport")
    _check(str(scene.get("open_picker").get("title_label").text) == "Ala - Joep Beving",
        "MIDI filename separators must render as normal punctuation")
    _check((scene.get("open_picker").get("measure") as SpinBox).max_value == 77,
        "Starting-point measure range must reflect the opened music")
    var jumps: HBoxContainer = modal.find_child("SourceMeasureQuickJumps", true, false) as HBoxContainer
    _check(jumps != null and jumps.get_child_count() == 3,
        "Measure picker needs visible Beginning, Middle and End shortcuts")
    if jumps != null and jumps.get_child_count() == 3:
        (jumps.get_child(2) as Button).pressed.emit()
        _check(int((scene.get("open_picker").get("measure") as SpinBox).value) == 77,
            "End shortcut selects the last source measure")
        (jumps.get_child(0) as Button).pressed.emit()
        _check(int((scene.get("open_picker").get("measure") as SpinBox).value) == 1,
            "Beginning shortcut returns to measure one")
    scene.call("_cancel_open_picker")
    _check(not preview_picker.visible and str(scene.get("current_screen")) == "library",
        "Cancel restores music selection instead of opening a lesson")
    scene.get("library_view").present_catalog({"pieces": [ {"id": "fixture.mid",
        "title": "A Very Long Piano Piece With a Complicated Name",
        "format": "MIDI", "folder": "Imported music"}], "warmups": []})
    var rows: VBoxContainer = scene.get("library_view").get("library_rows")
    var music_rows: Array[Button] = _library_entries(rows)
    _check(music_rows.size() == 1,
        "One score requires exactly one focusable music tile")
    if music_rows.size() == 1:
        var item: Button = music_rows[0]
        _check(item.get_node_or_null("MusicRowContent") != null and
            str(item.get_meta("library_title", "")).begins_with("A Very Long"),
            "Music row separates title and descriptive metadata")
        _check(item.tooltip_text.contains("Imported music"),
            "Clipped row keeps full source details in its tooltip")
        # During a long file check, changing progress counts should update
        # the message only. Recreating the focused music row on each poll
        # causes visible flicker and unexpected keyboard focus loss.
        scene.get("library_view").present_health({"started": true, "running": true,
            "checked": 1, "total": 10, "items": {}})
        item = _library_entries(rows)[0]
        scene.call("_on_library_health", 0, 200, PackedStringArray(),
            JSON.stringify({"started": true, "running": true,
                "checked": 2, "total": 10, "ok": 2, "warning": 0,
                "error": 0, "items": {}}).to_utf8_buffer())
        _check(rows.is_ancestor_of(item),
            "Checking another music file must not replace existing library rows")
    scene.call("_navigate", "practice")
    var cue: Control = scene.get("game_phase_cue")
    _check(cue != null and cue.get_parent() == score,
        "Transitions belong to a single small on-stage cue")
    _check(_in_viewport(cue, viewport), "Transition cue clips outside the stage")
    _check(_in_viewport(score, viewport), "Notation panel extends outside window")
    var illuminated: Control = scene.get("game_stage")
    var streak_meter: Control = scene.get("game_streak")
    _check(illuminated != null and illuminated.get_parent() == score,
        "The musical stage must be behind the real score, not a separate game simulation")
    _check(streak_meter != null and streak_meter.custom_minimum_size.x >= 120,
        "Three clean-pass indicators need a readable dedicated space")
    _check(streak_meter.size.y >= 20.0,
        "Clean-run indicators collapsed to an invisible line")
    _check(_in_viewport(streak_meter, viewport),
        "Game clean-run indicators leave the visible window")
    var three: Control = scene.get("practice_controls")
    _check(three.get_child_count() == 3,
        "The game must have only Retry, Play/Pause and Listen as transport controls")
    _check((scene.get("start_button") as Button).get_theme_stylebox("normal") is StyleBoxFlat,
        "Primary piano control must have a tactile custom skin")
    var retry: Button = scene.get("practice_retry_button")
    var primary: Button = scene.get("start_button")
    var listen: Button = scene.get("listen_button")
    _check(primary.size.y >= retry.size.y and primary.size.y >= listen.size.y,
        "Play is visually dominant, not another website-sized button")
    _check(retry.size.x >= 145.0 and listen.size.x >= 145.0,
        "Secondary game keys need real hit targets")
    _check(str(retry.get_meta("ui_button_role", "")) == "transport_retry" and
        str(primary.get_meta("ui_button_role", "")) == "transport_primary" and
        str(listen.get_meta("ui_button_role", "")) == "transport_listen",
        "Transport controls need separate identity and accessible action targets")
    var reset_face := retry.get_theme_stylebox("normal") as StyleBoxFlat
    var play_face := primary.get_theme_stylebox("normal") as StyleBoxFlat
    var listen_face := listen.get_theme_stylebox("normal") as StyleBoxFlat
    _check(reset_face.bg_color == listen_face.bg_color and
        play_face.bg_color != reset_face.bg_color,
        "Play has the single accent while Retry and Listen share neutral faces")
    _check(str(browse_button.get_meta("ui_button_role", "")) == "primary",
        "Choose music must use the primary action rather than a utility skin")
    var nav: Control = scene.get("practice_settings_button")
    _check(str(nav.get_meta("ui_button_role", "")) == "settings"
        and nav.get_theme_stylebox("normal").bg_color != play_face.bg_color,
        "Settings navigation stays neutral while Play holds the accent")
    _check((scene.get("practice_settings_button") as Button).focus_mode ==
        Control.FOCUS_ALL, "Navigation must stay keyboard accessible")
    _check(not (scene.get("practice_progress") as ProgressBar).visible,
        "A duplicate progress bar below the score must not compete with the stage rail")
    var brand: Label = scene.get("game_brand")
    _check(not brand.visible,
        "Practice keeps the piece title above music without a competing brand row")
    var count_in: Control = scene.get("game_count_in")
    count_in.present(-2.5, 3, true, false)
    _check(count_in.visible and int(count_in.get("count")) == 3,
        "Rhythmic prepare lights should use the piece's real meter")
    _check(_in_viewport(count_in, viewport),
        "Preparation lights must not leave the notation area")
    count_in.present(-2.0, 3, true, true)
    _check(not count_in.visible, "Preparation lights must freeze/disappear when paused")
    count_in.present(1.0, 3, true, false)
    _check(not count_in.visible, "No fake countdown once musical playing begins")

    # Wrong physical pitches attach to the original native source attack.
    # A page-coordinate ghost must never invent or displace source notation.
    var view: Control = scene.timeline_preview
    var atlas = load("res://tests/native_glyph_fixture.gd")
    _check(view.set_verovio_glyphs(atlas.catalogue(), atlas.note_catalogue(),
        atlas.tie_catalogue()), "Native feedback fixture loads source glyph assets")
    var attack := {"id":"engraved-head", "source_id":"real-attack", "kind":"note",
        "staff":"right", "voice":"1", "measure":1, "beat":0.0,
        "duration_beats":1.0, "note_type":"quarter", "dots":0,
        "is_attack":true, "spelling":{"step":"C","octave":4,"alter":0}}
    var model := {"schema":"piano-teacher-score-model-v1", "revision":11,
        "beat_unit":"quarter", "duration_beats":4.0, "active_hand":"right",
        "active_note_ids":["real-attack"], "notation_events":[attack],
        "notes":[{"id":"real-attack", "onset_beats":0.0, "duration_beats":1.0,
            "hand":"right", "midi_pitch":60}],
        "measures":[{"number":1, "start_beat":0.0, "end_beat":4.0,
            "meter":[4,4], "keys":{"right":0,"left":0},
            "clefs":{"right":{"sign":"G","line":2},"left":{"sign":"F","line":4}}}]}
    _check(view.load_score(model), "Native feedback fixture accepts source notation")
    var live_feedback: Control = scene.native_score_feedback
    live_feedback.bind_score(view, 11)
    live_feedback.present({"revision":11, "running":true, "phase":"playing",
        "transport_id":4, "midi_visual_events":[{"sequence":1, "transport_id":4,
            "reference_source_id":"real-attack", "status":"unexpected", "age":0.0}]})
    _check(live_feedback.pulses.size() == 1 and
        live_feedback.pulses[0].id == "engraved-head",
        "Wrong MIDI pitch attaches to the authentic source head")
    live_feedback.pulses[0]["until"] = Time.get_ticks_msec() - 2
    live_feedback._process(0.016)
    _check(live_feedback.pulses.is_empty(),
        "Expired native feedback vanishes while the score is stationary")
    live_feedback.present({"revision":11, "running":true, "phase":"playing",
        "transport_id":4, "midi_visual_events":[{"sequence":2, "transport_id":4,
            "reference_source_id":"unknown", "status":"unexpected", "age":0.0}]})
    _check(live_feedback.pulses.is_empty(), "Feedback cannot fabricate a missing source head")

    # Mapped notes belong on the engraved staff, not under a large red
    # rectangle. Reserve a small fallback warning for unmapped backend data.
    var hud: Control = scene.get("practice_note_feedback_panel")
    var hud_label: Label = scene.get("practice_note_feedback_label")
    scene.call("_update_note_feedback_hud", {"mode": "practice", "phase": "playing",
        "preview_only": false, "live_note_feedback":
        {"status": "missed", "pitch": 67, "name": "G4", "count": 1}})
    _check(not hud.visible, "Mapped missed note should not cover the engraved score")
    scene.call("_update_note_feedback_hud", {"mode": "practice", "phase": "playing",
        "preview_only": false, "live_note_feedback":
        {"status": "wrong", "pitch": 65, "name": "F4", "count": 1}})
    _check(not hud.visible, "Mapped wrong note should use a notehead outline, not the old HUD")
    scene.call("_update_note_feedback_hud", {"mode": "practice", "phase": "playing",
        "preview_only": true, "live_note_feedback": null})
    _check(not hud.visible, "Ungraded preview must not cover the sheet music")
    scene.call("_update_note_feedback_hud", {"mode": "practice", "phase": "feedback",
        "feedback_unmapped": 2, "preview_only": false})
    _check(not hud.visible, "Unmapped feedback must stay in the status line, not clip the score")
    scene.call("_update_note_feedback_hud", {"mode": "practice", "phase": "playing",
        "preview_only": false, "live_note_feedback": null})
    _check(not hud.visible, "Old feedback warning remains after clearing state")

    # Short library actions must not truncate ('Setting', 'Refres', etc.)
    # while intentionally long MIDI titles remain scroll-safe with ellipsis.
    scene.get("library_view").present_catalog({"pieces": [ {
        "id": "long.mid", "title": "Bill Evans on Autumn Leaves From the Album Portrait in Jazz",
        "folder": "", "format": "MIDI"}], "warmups": []})
    scene.call("_navigate", "library")
    await process_frame
    await process_frame
    var pages: Dictionary = scene.get("screens")
    var library_root: Control = pages["library"]
    var overlay: Control = scene.get("overlay_root")
    var drawer: Control = scene.get("overlay_drawer")
    _check(overlay.visible, "Library must be a visible dedicated view")
    _check(pages["practice"].visible,
        "Library navigation must keep the existing practice scene mounted")
    _check(drawer.get_global_rect().end.x <= viewport.x + 2.0,
        "Music drawer escapes right edge of the window")
    _check(drawer.get_global_rect().position.x >= -2.0,
        "Music drawer escapes left edge of the window")
    _check(drawer.size.x <= viewport.x + 2.0,
        "Music drawer cannot exceed available window width")
    _check(library_root.is_ancestor_of(scene.get("library_view").get("library_search")),
        "Music search remains inside the library content")
    var rail: Control = scene.get("navigation_rail")
    _check(rail != null and _in_viewport(rail, viewport),
        "The shared navigation rail remains fully inside the window")
    var destinations: Dictionary = scene.get("screen_navigation")
    for destination in ["library", "settings", "lesson"]:
        _check(destinations.has(destination), "Sidebar is missing destination " + destination)
        if destinations.has(destination):
            var destination_button: Button = destinations[destination]
            _check(destination_button.is_visible_in_tree() and _in_viewport(destination_button, viewport)
                and destination_button.focus_mode == Control.FOCUS_ALL,
                "Sidebar destination remains visible and keyboard accessible: " + destination)
            _check(bool(destination_button.get("is_selected")) == (destination == "library"),
                "Sidebar selection reflects the current Library view")
    var filter_timer: Timer = scene.get("library_view").get("library_filter_timer")
    _check(filter_timer != null and filter_timer.one_shot and
        absf(filter_timer.wait_time - .12) < .001,
        "Typing in a large library must coalesce UI row rebuilds")
    var short_buttons := 0
    for control in library_root.find_children("*", "Button", true, false):
        var button := control as Button
        if button.text in ["Refresh", "Check files",
                "Checking…", "Recheck files"]:
            short_buttons += 1
            _check(not button.clip_text, "Library short control clips text: " + button.text)
            _check(_in_viewport(button, viewport), "Library short control outside window: " + button.text)
            _check(button.size.x + 1.0 >= button.get_combined_minimum_size().x,
                "Library short control narrower than its text: " + button.text)
    _check(short_buttons == 2,
        "Library keeps Refresh and file-check actions alongside the shared sidebar")
    _check(str((scene.get("library_view").get("library_health_button") as Button).get_meta(
        "ui_button_role", "")) == "settings",
        "Library diagnostics require a distinguishable inspection action")
    var library_items: Control = scene.get("library_view").get("library_rows")
    var library_status: Label = scene.get("library_view").get("library_message")
    _check(library_status.get_global_rect().position.y < library_items.get_global_rect().position.y,
        "Library import failures must appear above the score rows, not below a full screen")
    var found_long_title := false
    for control in _library_entries(library_items):
        if control is Button and "Bill Evans" in str(control.get_meta("library_title", "")):
            found_long_title = true
            var title_ink: Label = control.find_child("MusicTitle", true, false) as Label
            _check(title_ink != null and title_ink.clip_text and
                title_ink.text_overrun_behavior == TextServer.OVERRUN_TRIM_ELLIPSIS,
                "Long music titles must clip independently of their metadata")
            _check(control.tooltip_text.contains(
                "Bill Evans on Autumn Leaves From the Album Portrait in Jazz"),
                "Long library title tooltip lost its complete name")
    _check(found_long_title, "Synthetic long title missing from library")
    var health_entry := "long.mid"
    var diagnostics := {"started": true, "running": false,
        "checked": 1, "total": 1, "ok": 0, "warning": 1, "error": 0,
        "items": {health_entry: {"status": "warning", "notes": 42, "measures": 16,
            "message": "Ignored an unmatched release"}}}
    scene.call("_on_library_health", 0, 200, PackedStringArray(),
        JSON.stringify(diagnostics).to_utf8_buffer())
    await process_frame
    var health_label: Label = scene.get("library_view").get("library_health_label")
    var health_button: Button = scene.get("library_view").get("library_health_button")
    _check(health_label.visible and "1 repaired" in health_label.text,
        "Library health summary must explain repairs")
    _check(not health_button.disabled, "Recheck should be available after scan completes")
    var flagged := false
    for control in _library_entries(library_items):
        if control is Button and str(control.get_meta("library_status", "")) == "warning":
            flagged = control.tooltip_text.contains("Ignored an unmatched release") \
                and control.tooltip_text.contains("42 notes · 16 measures") \
                and str(control.get_meta("library_title", "")).contains("Bill Evans")
    _check(flagged, "The repaired MIDI row must explain its specific import warning")
    diagnostics["running"] = true
    scene.call("_on_library_health", 0, 200, PackedStringArray(),
        JSON.stringify(diagnostics).to_utf8_buffer())
    _check(health_button.disabled, "File check should not restart while still scanning")
    # Validate the real card grid, not just a configured column count. Wide
    # views show two tiles per row; compact views retain a single readable tile.
    scene.get("library_view").present_catalog({"warmups": [], "pieces": [
        {"id": "a.mid", "title": "First piece", "format": "MIDI"},
        {"id": "b.mid", "title": "Second piece", "format": "MIDI"},
        {"id": "c.mid", "title": "Third piece", "format": "MIDI"}]})
    for frame in range(6):
        await process_frame
    var tiles := _library_entries(library_items)
    _check(tiles.size() == 3, "Card layout must retain all actual music entries")
    if tiles.size() == 3:
        var first: Rect2 = tiles[0].get_global_rect()
        var second: Rect2 = tiles[1].get_global_rect()
        var third: Rect2 = tiles[2].get_global_rect()
        _check(second.position.y >= first.end.y - 1.0
            and third.position.y >= second.end.y - 1.0,
            "Music shelf uses full readable rows without overlapping titles")
        for tile in tiles:
            _check(tile.get_global_rect().position.x >= library_root.get_global_rect().position.x - 1.0
                and tile.get_global_rect().end.x <= library_root.get_global_rect().end.x + 1.0,
                "Music tile must fit the dedicated content area")
    scene.call("_navigate", "practice")
    await process_frame
    await process_frame

    # Regression for the user's real 1536x960 screenshot: opening Settings
    # must not show only a narrow slice of its wide contents. Check the
    # actual Godot-placed fields, not merely the panel's outer bounds.
    scene.call("_navigate", "settings")
    await process_frame
    await process_frame
    var settings_panel: Control = scene.get("overlay_drawer")
    var settings_page: Control = pages["settings"]
    _check(overlay.visible and settings_page.is_visible_in_tree(),
        "Settings must open as a readable contextual sheet")
    _check(settings_panel.size.x >= minf(viewport.x, 500.0) - 2.0,
        "Settings drawer narrowed to a clipped strip")
    print("SETTINGS_DEBUG: panel_rect=", settings_panel.get_global_rect(), " viewport=", viewport)
    _check(_in_viewport(settings_panel, viewport),
        "Settings drawer overflows the viewport")
    var essential: Array[Control] = [
        scene.get("settings_view").get("folder_edit"), scene.get("settings_view").get("device_button"),
        scene.get("settings_view").get("tempo_setting"), scene.get("settings_view").get("apply_tempo_button"),
        scene.get("settings_view").get("metronome_toggle"), scene.get("settings_view").get("fullscreen_toggle")]
    for field in essential:
        var rect: Rect2 = field.get_global_rect()
        _check(rect.position.x >= settings_panel.get_global_rect().position.x - 2.0
            and rect.end.x <= viewport.x + 2.0,
            "Settings control clipped horizontally: " + field.name)
        _check(field.size.x >= 80.0,
            "Settings control too narrow to use: " + field.name)
    for control in settings_page.find_children("*", "Button", true, false):
        if control.is_visible_in_tree():
            _check(control.get_global_rect().end.x <= viewport.x + 2.0,
                "Settings button disappears beyond right edge: " + control.text)
            _check(control.size.x + 2.0 >= control.get_combined_minimum_size().x,
                "Settings button text clipped: " + control.text)
    scene.call("_navigate", "practice")
    await process_frame
    await process_frame

    # Imported MIDI starting-point dialog must expose the entire source,
    # synchronize slider and editable measure, and remain usable without MIDI.
    scene.call("_show_open_picker", {
        "title": "Long Imported Piano Piece",
        "piece_last_bar": 128,
        "selected_start_bar": 87
    })
    await process_frame
    var picker: Control = scene.get("open_picker")
    var measure: SpinBox = scene.get("open_picker").get("measure")
    var slider: HSlider = scene.get("open_picker").get("measure_slider")
    var start_mode: OptionButton = scene.get("open_picker").get("mode_choice")
    _check(picker.visible, "MIDI opening did not present a starting-measure selector")
    _check(measure.max_value == 128 and measure.min_value == 1,
        "Starting-measure selector does not cover the entire MIDI piece")
    _check(measure.value == 87 and slider.value == 87,
        "The saved source measure was not selected")
    _check(start_mode.item_count == 2,
        "MIDI opening must offer both Learn Notes and Practice Rhythm")
    measure.value = 104
    _check(slider.value == 104, "Measure spinner did not synchronize the timeline")
    slider.value = 23
    _check(measure.value == 23, "Measure timeline did not synchronize the spinner")
    picker.hide()

    scene.call("_update_hand_stages", {"hand_stages": [
        {"hand": "left", "active": false, "complete": true, "locked": false},
        {"hand": "right", "active": true, "complete": false, "locked": false},
        {"hand": "both", "active": false, "complete": false, "locked": true}]})
    var ribbon: Control = scene.get("practice_stage_bar")
    var stage_labels: Dictionary = scene.get("practice_stage_labels")
    _check(ribbon.visible,
        "Hand progression stays in the stage without consuming a layout row")
    _check(stage_labels["left"].text.begins_with("✓")
        and stage_labels["right"].text.begins_with("●")
        and "locked" in stage_labels["both"].text.to_lower(),
        "The hand progression does not show completed, current and locked stages")
    scene.call("_update_hand_stages", {"hand_stages": []})
    _check(not ribbon.visible, "Hand ribbon should disappear when no hand course exists")

    # Stage chips describe the current exercise and hand, not every level
    # that appears anywhere else in the course. Numbers stay consecutive.
    scene.set("last_state", {"title": "Current piece", "lesson_level": "original"})
    scene.call("_navigate", "lesson")
    scene.call("_on_lesson", 0, 200, PackedStringArray(), JSON.stringify({
        "current_step": 2, "completed_steps": 0, "total_steps": 4, "steps": [
            {"number": 1, "exercise": 1, "hand": "right", "level": "skeleton", "first_bar": 1, "last_bar": 2},
            {"number": 2, "exercise": 2, "hand": "right", "level": "original", "first_bar": 3, "last_bar": 4},
            {"number": 3, "exercise": 1, "hand": "right", "level": "outline", "first_bar": 1, "last_bar": 2},
            {"number": 4, "exercise": 2, "hand": "left", "level": "skeleton", "first_bar": 3, "last_bar": 4}]
        }).to_utf8_buffer())
    await process_frame
    var levels: Dictionary = scene.get("lesson_stage_labels")
    _check(levels["original"].is_visible_in_tree() and levels["original"].text == "1. Original"
        and not levels["skeleton"].visible and not levels["outline"].visible,
        "Lesson stages must show only the current exercise/hand's available Original as stage 1")
    scene.call("_navigate", "practice")

    # Review both missed chord pitches and the *played* wrong note.
    # Test actual dialog controls and section retry widgets, not a static label.
    var report: Dictionary = {
        "accuracy_percent": 50.0, "correct": 2, "total": 4,
        "missed": 1, "wrong": 1, "extra_notes": 1,
        "early": 0, "late": 0, "short": 1, "long": 0,
        "sections": [ {
            "first_bar": 3, "last_bar": 4, "start_beat": 8.0, "end_beat": 16.0,
            "errors": 3, "issues": [
                {"bar": 3, "status": "missed", "pitch": 60, "name": "C4"},
                {"bar": 3, "status": "wrong", "pitch": 64, "name": "E4",
                 "played_pitch": 66, "played_name": "F#4"},
                {"bar": 4, "status": "short", "pitch": 67, "name": "G4"}
            ]}]}
    var review: AcceptDialog = scene.get("review_sheet")
    review.call("open_review", report)
    await process_frame
    var review_summary: Label = review.get("summary_label")
    var review_rows: VBoxContainer = review.get("section_list")
    _check(review.visible and "50%" in review_summary.text,
        "Review dialog did not show assessed accuracy")
    _check(review_rows.get_child_count() == 1,
        "Review dialog did not show a source-measure section")
    _check("Expected E4, played F#4" in review.call("_issue_text", report["sections"][0]["issues"][1]),
        "Review omits the actual incorrect piano key")
    var review_buttons := review_rows.find_children("*", "Button", true, false)
    _check(review_buttons.size() == 1 and "3" in review_buttons[0].text,
        "Review lacks a direct retry button for the assessed section")
    review.hide()

    var pause: Control = scene.get("pause_sheet")
    pause.call("present", {"paused": true, "mode": "practice", "bpm": 68,
        "hand": "left", "hands": ["left", "right", "both"],
        "first_bar": 1, "last_bar": 8, "seek_available": true,
        "seek_range": {"first_bar": 1, "last_bar": 8}})
    await process_frame
    await process_frame
    var panel: Control = pause.get("modal_panel")
    var resume: Control = pause.get("resume_button")
    print("PHASE2_PAUSE_DIAGNOSTIC: window=", viewport, " panel=", panel.get_global_rect(),
        " resume=", resume.get_global_rect())
    _check(_in_viewport(panel, viewport), "Pause panel extends outside window")
    _check(_in_viewport(resume, viewport), "Resume button not visible")
    _check(resume.size.y >= 50.0, "Pause resume button too small")
    _check(scene.find_children("*", "HTTPRequest", true, false).is_empty(),
        "Layout-only smoke must not create backend HTTP requests")
    for failure in failures:
        push_error("PHASE2_UI_FAIL: " + failure)
    if failures.is_empty():
        print("PHASE2_UI_PASS: ", viewport.x, "x", viewport.y,
            " · score ", score.size, " · modal ", panel.size)
    quit(1 if not failures.is_empty() else 0)
