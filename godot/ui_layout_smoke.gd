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
    _check(_in_viewport(score, viewport), "Notation panel extends outside window")

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

    # The same real HUD code used by state polling must make missing
    # feedback readable without waiting for a physical piano.
    var hud: Control = scene.get("practice_note_feedback_panel")
    var hud_label: Label = scene.get("practice_note_feedback_label")
    scene.call("_update_note_feedback_hud", {"mode": "practice", "phase": "playing",
        "preview_only": false, "live_note_feedback":
        {"status": "missed", "pitch": 67, "name": "G4", "count": 1}})
    _check(hud.visible and "MISSED" in hud_label.text and "G4" in hud_label.text,
        "A missed note is not visible in the practice HUD")
    _check(_in_viewport(hud, viewport), "Missing-note feedback HUD is clipped")
    scene.call("_update_note_feedback_hud", {"mode": "practice", "phase": "playing",
        "preview_only": false, "live_note_feedback":
        {"status": "wrong", "pitch": 65, "name": "F4", "count": 1}})
    _check(hud.visible and "WRONG" in hud_label.text and "F4" in hud_label.text,
        "Wrong-note feedback is not visible in the practice HUD")
    scene.call("_update_note_feedback_hud", {"mode": "practice", "phase": "playing",
        "preview_only": true, "live_note_feedback": null})
    _check(hud.visible and "SCORING OFF" in hud_label.text,
        "Preview mode does not visibly explain why misses are unavailable")
    scene.call("_update_note_feedback_hud", {"mode": "practice", "phase": "playing",
        "preview_only": false, "live_note_feedback": null})
    _check(not hud.visible, "Old missed note remains visible after clearing feedback")
    
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
    var library_items: Control = scene.get("library_rows")
    var library_status: Label = scene.get("library_message")
    _check(library_status.get_global_rect().position.y < library_items.get_global_rect().position.y,
        "Library import failures must appear above the score rows, not below a full screen")
    var found_long_title := false
    for control in library_items.get_children():
        if control is Button and "Bill Evans" in str((control as Button).text):
            found_long_title = true
            _check((control as Button).clip_text, "Long library titles must use ellipsis")
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
        if control is Button and "[REPAIRED]" in control.text:
            flagged = "unmatched release" in control.tooltip_text
    _check(flagged, "The repaired MIDI row must explain its specific import warning")
    diagnostics["running"] = true
    scene.call("_on_library_health", 0, 200, PackedStringArray(),
        JSON.stringify(diagnostics).to_utf8_buffer())
    _check(health_button.disabled, "File check should not restart while still scanning")
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
    var picker: ConfirmationDialog = scene.get("open_picker")
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
