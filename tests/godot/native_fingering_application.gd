extends SceneTree

var failures: Array = []

func _initialize() -> void:
    call_deferred("_run")

func _settle(app: Control, after_revision: int = -1) -> bool:
    var deadline: int = Time.get_ticks_msec()+25000
    while Time.get_ticks_msec() < deadline:
        await process_frame
        if app.rendered_revision > after_revision and app._native_score_ready() and \
                not app.timeline_preview.annotations.drawn_fingerings.is_empty() and not app.action_pending:
            await process_frame
            await RenderingServer.frame_post_draw
            return true
    failures.append("Native app did not become ready: "+str(app.score_error))
    push_error(failures[-1]+" "+str({"rendered":app.rendered_revision,
        "ready":app._native_score_ready(),"pending":app.action_pending,
        "size":app.timeline_preview.size,"labels":app.timeline_preview.annotations.drawn_fingerings.size(),
        "layout":app.timeline_preview.annotations.fingering_layout.size(),
        "same_layout":is_same(app.timeline_preview.layout,app.timeline_preview.annotations.score_layout),
        "indices":[app.timeline_preview.layout.ordered_events.size(),app.timeline_preview.annotations.score_layout.ordered_events.size()],
        "assigned":app.timeline_preview.layout.ordered_events[0].get("fingering") if not app.timeline_preview.layout.ordered_events.is_empty() else null,
        "issues":app.timeline_preview.annotations.fingering_placement_issues,
        "enabled":app.timeline_preview.annotations.fingering_annotations_enabled,
        "running":app.last_state.get("running"),"phase":app.last_state.get("phase")}))
    return false

func _run() -> void:
    root.size = Vector2i(1280,800)
    var app = load("res://main.gd").new()
    root.add_child(app)
    app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    app._navigate("practice")
    if not app.has_method("_on_fingering_change_requested"):
        push_error("Production app has no fingering POST handler")
        quit(1)
        return
    if not await _settle(app):
        quit(1)
        return
    # The complete path arrives independently of the initial score. Long
    # sources must finish building it before the memory assertion or edits.
    var path_deadline: int = Time.get_ticks_msec()+25000
    while (app.lesson_pending or app.practice_step_entries.is_empty()) and Time.get_ticks_msec() < path_deadline:
        await process_frame
    if app.lesson_pending or app.practice_step_entries.is_empty():
        failures.append("Complete lesson path did not become ready")
    var folder: String = OS.get_cmdline_user_args()[0]
    var renderer: Control = app.timeline_preview
    var first: Dictionary = renderer.annotations.drawn_fingerings[0]
    var id: String = first["event_ids"][0]
    var source: String = renderer.FingeringPlacement.source(renderer.layout.expression_note_index[id])
    var previous: int = int(first["finger"])
    var changed: int = previous % 5+1
    var revision: int = app.rendered_revision
    var finger_rect: Rect2 = renderer.get_global_transform_with_canvas()*first["rect"]
    finger_rect.position *= root.content_scale_factor
    finger_rect.size *= root.content_scale_factor
    root.get_texture().get_image().save_png(folder.path_join("app-before.png"))
    var click := InputEventMouseButton.new()
    click.button_index = MOUSE_BUTTON_RIGHT
    click.pressed = true
    click.position = renderer.get_global_transform_with_canvas()*first["rect"].get_center()
    root.push_input(click,true)
    await process_frame
    if renderer.annotations.fingering_popup == null or not renderer.annotations.fingering_popup.visible:
        failures.append("App right click did not open the fingering editor")
    else:
        renderer.annotations.fingering_popup.id_pressed.emit(changed)
    if app.last_post_path != "/fingering":
        failures.append("Popup must POST /fingering through the production action request")
    if app.action_request.timeout < 300.0:
        failures.append("Whole-piece inference must not inherit the short control request timeout")
    print("FINGERING_APPLICATION_EDIT:",source)
    if not await _settle(app,revision):
        quit(1)
        return
    var corrected := false
    for event in app.timeline_preview.layout.ordered_events:
        if event.get("source_id") == source and event.get("is_attack",false):
            corrected = event.get("fingering",{}).get("finger") == changed and \
                event.get("fingering",{}).get("origin") == "manual"
    if not corrected:
        failures.append("API correction did not reach the refreshed native score")
    root.get_texture().get_image().save_png(folder.path_join("app-corrected.png"))
    revision = app.rendered_revision
    print("FINGERING_APPLICATION_RESTORE:",source)
    app._on_fingering_change_requested(source,null)
    if not await _settle(app,revision):
        quit(1)
        return
    var restored := false
    for event in app.timeline_preview.layout.ordered_events:
        if event.get("source_id") == source and event.get("is_attack",false):
            restored = event.get("fingering",{}).get("finger") == previous and \
                event.get("fingering",{}).get("origin") != "manual"
    if not restored:
        failures.append("Removing the correction did not restore the production assignment")
    app._present_fingering_status({"status":"partial","unknown":6,"assigned":12})
    if not app.fingering_status_label.visible or "6" not in app.fingering_status_label.text or \
            "Right-click" not in app.fingering_status_label.tooltip_text:
        failures.append("Partial predictions need a minimal count and editing help")
    app._present_fingering_status({"status":"unavailable","unknown":18,"error":"Offline runtime missing"})
    if "unavailable" not in app.fingering_status_label.text or \
            "Offline runtime missing" not in app.fingering_status_label.tooltip_text:
        failures.append("Unavailable fingering needs an actionable provider-neutral status")
    app._present_fingering_status({"status":"ready","unknown":0})
    if app.fingering_status_label.visible and app.timeline_preview.annotations.fingering_placement_issues.is_empty():
        failures.append("Available automatic predictions should not add status clutter")
    var placement_issues: Array = app.timeline_preview.annotations.fingering_placement_issues.duplicate(true)
    app.timeline_preview.annotations.fingering_placement_issues = [{"source_id":source,"reason":"No local space"}]
    app._present_fingering_status({"status":"ready","unknown":0})
    if not app.fingering_status_label.visible or "1 fingering needs space" != app.fingering_status_label.text or \
            "Enlarge" not in app.fingering_status_label.tooltip_text:
        failures.append("Unfit annotations must be reported with actionable space guidance")
    for summary in [{"status":"partial","unknown":6},{"status":"partial","unknown":0,"review":2},
            {"status":"unavailable","error":"Offline runtime missing"}]:
        app._present_fingering_status(summary)
        if "1 needs space" not in app.fingering_status_label.text or "Enlarge" not in app.fingering_status_label.tooltip_text:
            failures.append("Unknown/review/provider status must not hide unfit annotations")
    app.timeline_preview.annotations.fingering_placement_issues = placement_issues
    app._present_fingering_status({"status":"partial","unknown":0,"review":2,
        "issues":["Two fixed notes require the same finger"]})
    if not app.fingering_status_label.visible or "2" not in app.fingering_status_label.text or \
            "Two fixed notes" not in app.fingering_status_label.tooltip_text:
        failures.append("Conflicting fixed assignments need a review count and explanation")
    var current: Dictionary = app.last_state.duplicate(true)
    app.last_state["revision"] = app.revision+1
    app.last_state["piece_fingerprint"] = "another-loaded-piece"
    app.last_post_path = "stale-target-control"
    app._on_fingering_change_requested(source,changed)
    if app.action_pending or app.last_post_path != "stale-target-control":
        failures.append("An old native view cannot correct a newly loaded piece")
    app.last_state = current
    var file := FileAccess.open(folder.path_join("app-report.json"),FileAccess.WRITE)
    file.store_string(JSON.stringify({"source_id":source,"before":previous,"changed":changed,
        "revision":app.rendered_revision,"failures":failures,
        "static_memory":OS.get_static_memory_usage(),"path_steps":app.practice_step_entries.size(),
        "finger_rect":[finger_rect.position.x,finger_rect.position.y,finger_rect.size.x,finger_rect.size.y]}))
    for failure in failures:
        push_error(failure)
    print("NATIVE_FINGERING_APPLICATION_FAILURES:",failures.size())
    quit(0 if failures.is_empty() else 1)
