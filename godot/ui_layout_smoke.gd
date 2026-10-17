extends SceneTree

# Actual Godot container geometry smoke, without a backend or piano.
# Re-run at 1536x960, 1024x768 and 800x600. Reject clipped transport
# buttons and pause panels rather than relying on Python unit tests.
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
    var scene = load("res://main.tscn").instantiate()
    root.add_child(scene)
    await process_frame
    scene.call("_navigate", "practice")
    await process_frame
    await process_frame
    var viewport: Vector2 = root.size
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
    scene.call("_show_open_picker", {"title":"Ala_-_Joep_Beving",
        "piece_last_bar":77, "selected_start_bar":1})
    await process_frame
    await process_frame
    var preview_picker: Control = scene.get("open_picker")
    var modal: PanelContainer = scene.get("open_panel")
    _check(preview_picker.visible and not scene.get("overlay_root").visible,
        "Starting point must hide the library drawer behind its modal")
    _check(modal.size.x >= minf(500.0, viewport.x-36.0) and
        modal.size.y < viewport.y*.90,
        "Starting point must be broad and compact, not a tall thin window")
    _check(absf(modal.get_global_rect().get_center().x-viewport.x*.5) < 6.0 and
        absf(modal.get_global_rect().get_center().y-viewport.y*.5) < 6.0,
        "Starting point modal must be centered in the real viewport")
    _check(str(scene.get("open_title").text) == "Ala - Joep Beving",
        "MIDI filename separators must render as normal punctuation")
    _check((scene.get("open_measure") as SpinBox).max_value == 77,
        "Starting-point measure range must reflect the opened music")
    var jumps: HBoxContainer = modal.find_child("SourceMeasureQuickJumps", true, false) as HBoxContainer
    _check(jumps != null and jumps.get_child_count() == 3,
        "Measure picker needs visible Beginning, Middle and End shortcuts")
    if jumps != null and jumps.get_child_count() == 3:
        (jumps.get_child(2) as Button).pressed.emit()
        _check(int((scene.get("open_measure") as SpinBox).value) == 77,
            "End shortcut selects the last source measure")
        (jumps.get_child(0) as Button).pressed.emit()
        _check(int((scene.get("open_measure") as SpinBox).value) == 1,
            "Beginning shortcut returns to measure one")
    scene.call("_cancel_open_picker")
    _check(not preview_picker.visible and str(scene.get("current_screen")) == "library",
        "Cancel restores music selection instead of opening a lesson")
    scene.set("library_info", {"pieces":[{"id":"fixture.mid",
        "title":"A Very Long Piano Piece With a Complicated Name",
        "format":"MIDI", "folder":"Imported music"}], "warmups":[]})
    scene.call("_populate_library")
    var rows: VBoxContainer = scene.get("library_rows")
    var music_rows: Array = rows.find_children("*", "Button", true, false)
    _check(music_rows.size() == 1,
        "One score requires exactly one focusable full-width library action")
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
        scene.set("library_health_info", {"started":true, "running":true,
            "checked":1, "total":10, "items":{}})
        scene.call("_on_library_health", 0, 200, PackedStringArray(),
            JSON.stringify({"started":true, "running":true,
                "checked":2, "total":10, "ok":2, "warning":0,
                "error":0, "items":{}}).to_utf8_buffer())
        _check(item.get_parent() == rows,
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
    _check(reset_face.bg_color != play_face.bg_color and
        reset_face.bg_color != listen_face.bg_color and
        listen_face.bg_color != play_face.bg_color,
        "Play, Retry and Listen must have distinguishable base colours")
    _check(str(browse_button.get_meta("ui_button_role", "")) == "primary",
        "Choose music must use the primary action rather than a utility skin")
    var nav: Control = scene.get("practice_settings_button")
    _check(str(nav.get_meta("ui_button_role", "")) == "utility",
        "Navigation must not have the same visual priority as transport")
    _check((scene.get("practice_settings_button") as Button).focus_mode ==
        Control.FOCUS_ALL, "Navigation must stay keyboard accessible")
    _check(not (scene.get("practice_progress") as ProgressBar).visible,
        "A duplicate progress bar below the score must not compete with the stage rail")
    var brand: Label = scene.get("game_brand")
    _check(brand.visible == (viewport.x >= 1280.0),
        "Decorative game brand must collapse before it crowds piano controls")
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

    # Check wrong physical pitches use the real staff's pitch spacing and
    # do not move a correct chord note or invent a separate score location.
    scene.set("score_layout", {"systems": [{
        "page": 0, "left": 0.05, "right": 0.95,
        "staff_lines": [0.10, 0.12, 0.14, 0.16, 0.18,
                        0.30, 0.32, 0.34, 0.36, 0.38]
    }]})
    var ghost: Dictionary = scene.call("_wrong_note_ghost", 62,
        {"id": "real-attack", "pitch": 60, "page": 0,
         "x": 0.3, "y": 0.14, "hand": "right"})
    _check(not ghost.is_empty(), "An adjacent wrong pitch was not positioned on the staff")
    if not ghost.is_empty():
        _check(absf(float(ghost["y"]) - 0.13) < 0.0001,
            "Wrong pitch should be exactly one diatonic step above C")
        _check(str(ghost["label"]) == "D4", "Wrong staff note label incorrect")
    var outside: Dictionary = scene.call("_wrong_note_ghost", 75,
        {"id": "real-attack", "pitch": 60, "page": 1,
         "x": 0.3, "y": 0.14, "hand": "right"})
    _check(outside.is_empty(), "Wrong note must not fabricate a missing source staff")
    var live_overlay: Control = scene.get("score_overlay")
    live_overlay.wrong_ghosts.append({"until_ms": Time.get_ticks_msec()-2,
        "page":0, "x":0.3, "y":0.14, "label":"D4"})
    live_overlay.hit_pulses.append({"until_ms":Time.get_ticks_msec()-2,
        "page":0, "x":0.3, "y":0.14, "status":"on_time"})
    scene.call("_process", 0.016)
    _check(live_overlay.wrong_ghosts.is_empty() and live_overlay.hit_pulses.is_empty(),
        "Expired played-note ghosts must vanish even while the score is stationary")

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
    scene.set("library_info", {"pieces": [{
        "id": "long.mid", "title": "Bill Evans on Autumn Leaves From the Album Portrait in Jazz",
        "folder": "", "format": "MIDI"}], "warmups": []})
    scene.call("_populate_library")
    scene.call("_navigate", "library")
    await process_frame
    await process_frame
    var pages: Dictionary = scene.get("screens")
    var library_root: Control = pages["library"]
    var overlay: Control = scene.get("overlay_root")
    var drawer: Control = scene.get("overlay_drawer")
    _check(overlay.visible, "Browse library must be a visible in-context drawer")
    _check(pages["practice"].visible,
        "Music library must not replace or blank the sheet music")
    _check(drawer.get_global_rect().end.x <= viewport.x + 2.0,
        "Music drawer escapes right edge of the window")
    _check(drawer.get_global_rect().position.x >= -2.0,
        "Music drawer escapes left edge of the window")
    _check(drawer.size.x <= viewport.x + 2.0,
        "Music drawer cannot exceed available window width")
    _check(library_root.is_ancestor_of(scene.get("library_search")),
        "Music search remains inside the library drawer")
    var short_buttons := 0
    for control in library_root.find_children("*", "Button", true, false):
        var button := control as Button
        if button.text in ["Close", "Settings", "Refresh", "Check files"]:
            short_buttons += 1
            _check(not button.clip_text, "Library short control clips text: " + button.text)
            _check(_in_viewport(button, viewport), "Library short control outside window: " + button.text)
            _check(button.size.x + 1.0 >= button.get_combined_minimum_size().x,
                "Library short control narrower than its text: " + button.text)
    _check(short_buttons == 4, "Expected Close, Settings, Refresh and Check files actions")
    _check(str((scene.get("library_health_button") as Button).get_meta(
        "ui_button_role", "")) == "settings",
        "Library diagnostics require a distinguishable inspection action")
    var library_items: Control = scene.get("library_rows")
    var library_status: Label = scene.get("library_message")
    _check(library_status.get_global_rect().position.y < library_items.get_global_rect().position.y,
        "Library import failures must appear above the score rows, not below a full screen")
    var found_long_title := false
    for control in library_items.get_children():
        if control is Button and "Bill Evans" in str(control.get_meta("library_title", "")):
            found_long_title = true
            var title_ink: Label = control.find_child("MusicTitle", true, false) as Label
            _check(title_ink != null and title_ink.clip_text and
                title_ink.text_overrun_behavior == TextServer.OVERRUN_TRIM_ELLIPSIS,
                "Long music titles must clip independently of their metadata")
            _check((control as Button).tooltip_text.contains("Portrait in Jazz"),
                "Long library title tooltip lost its complete name")
    _check(found_long_title, "Synthetic long title missing from library")
    var health_entry := "long.mid"
    var diagnostics := {"started":true, "running":false,
        "checked":1, "total":1, "ok":0, "warning":1, "error":0,
        "items":{health_entry:{"status":"warning", "notes":42, "measures":16,
            "message":"Ignored an unmatched release"}}}
    scene.call("_on_library_health", 0, 200, PackedStringArray(),
        JSON.stringify(diagnostics).to_utf8_buffer())
    await process_frame
    var health_label: Label = scene.get("library_health_label")
    var health_button: Button = scene.get("library_health_button")
    _check(health_label.visible and "1 repaired" in health_label.text,
        "Library health summary must explain repairs")
    _check(not health_button.disabled, "Recheck should be available after scan completes")
    var flagged := false
    for control in library_items.get_children():
        if control is Button and str(control.get_meta("library_status", "")) == "warning":
            flagged = "unmatched release" in control.tooltip_text
    _check(flagged, "The repaired MIDI row must explain its specific import warning")
    diagnostics["running"] = true
    scene.call("_on_library_health", 0, 200, PackedStringArray(),
        JSON.stringify(diagnostics).to_utf8_buffer())
    _check(health_button.disabled, "File check should not restart while still scanning")
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
    _check(_in_viewport(settings_panel, viewport),
        "Settings drawer overflows the viewport")
    var essential: Array[Control] = [
        scene.get("folder_edit"), scene.get("device_button"),
        scene.get("tempo_setting"), scene.get("apply_tempo_button"),
        scene.get("metronome_toggle"), scene.get("fullscreen_toggle")]
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
    var measure: SpinBox = scene.get("open_measure")
    var slider: HSlider = scene.get("open_measure_slider")
    var start_mode: OptionButton = scene.get("open_mode")
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
        {"hand":"left", "active":false, "complete":true, "locked":false},
        {"hand":"right", "active":true, "complete":false, "locked":false},
        {"hand":"both", "active":false, "complete":false, "locked":true}]})
    var ribbon: Control = scene.get("practice_stage_bar")
    var stage_labels: Dictionary = scene.get("practice_stage_labels")
    _check(ribbon.visible, "Hand progression must be visible while practising")
    _check("DONE" in stage_labels["left"].text
        and "NOW" in stage_labels["right"].text
        and "LOCKED" in stage_labels["both"].text,
        "The hand progression does not show completed, current and locked stages")
    scene.call("_update_hand_stages", {"hand_stages": []})
    _check(not ribbon.visible, "Hand ribbon should disappear when no hand course exists")

    # Review both missed chord pitches and the *played* wrong note.
    # Test actual dialog controls and section retry widgets, not a static label.
    var report: Dictionary = {
        "accuracy_percent": 50.0, "correct": 2, "total": 4,
        "missed": 1, "wrong": 1, "extra_notes": 1,
        "early": 0, "late": 0, "short": 1, "long": 0,
        "sections": [{
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
    pause.call("present", {"paused":true, "mode":"practice", "bpm":68,
        "hand":"left", "hands":["left","right","both"],
        "first_bar":1, "last_bar":8, "seek_available":true,
        "seek_range":{"first_bar":1,"last_bar":8}})
    await process_frame
    await process_frame
    var panel: Control = pause.get("modal_panel")
    var resume: Control = pause.get("resume_button")
    print("PHASE2_PAUSE_DIAGNOSTIC: window=", viewport, " panel=", panel.get_global_rect(),
        " resume=", resume.get_global_rect())
    _check(_in_viewport(panel, viewport), "Pause panel extends outside window")
    _check(_in_viewport(resume, viewport), "Resume button not visible")
    _check(resume.size.y >= 50.0, "Pause resume button too small")
    for failure in failures:
        push_error("PHASE2_UI_FAIL: " + failure)
    if failures.is_empty():
        print("PHASE2_UI_PASS: ", viewport.x, "x", viewport.y,
            " · score ", score.size, " · modal ", panel.size)
    quit(1 if not failures.is_empty() else 0)
