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
