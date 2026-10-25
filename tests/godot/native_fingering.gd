extends SceneTree

var checks: Array = []
var requests: Array = []
var folder: String

func _initialize() -> void:
    call_deferred("_run")

func _capture(view: SubViewport, renderer: Control, name: String) -> void:
    renderer.queue_redraw()
    await process_frame
    await process_frame
    await RenderingServer.frame_post_draw
    view.get_texture().get_image().save_png(folder.path_join(name))

func _frame(view: SubViewport, renderer: Control, model: Dictionary, clock: float, name: String) -> Dictionary:
    renderer.load_score(model)
    renderer.show_fingerings = true
    renderer.present({"running":true, "paused":true, "hand":"both"}, clock)
    await _capture(view, renderer, name+".png")
    var labels: Array = []
    if renderer.get("drawn_fingerings") is Array:
        for item in renderer.drawn_fingerings:
            var rect: Rect2 = item["rect"]
            var head: Vector2 = item["head"]
            labels.append({"rect":[rect.position.x,rect.position.y,rect.size.x,rect.size.y],
                "head":[head.x,head.y], "finger":item["finger"], "hand":item["hand"],
                "event_ids":item["event_ids"]})
    renderer.show_fingerings = false
    await _capture(view, renderer, name+"-base.png")
    renderer.show_fingerings = true
    return {"file":name+".png", "base":name+"-base.png", "labels":labels}

func _run() -> void:
    var args := OS.get_cmdline_user_args()
    folder = args[1]
    var fixture: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
    var view := SubViewport.new()
    view.size = Vector2i(1536,520)
    view.render_target_update_mode = SubViewport.UPDATE_ALWAYS
    root.add_child(view)
    var renderer = load("res://../tests/godot/native_fingering_view.gd").new()
    renderer.size = Vector2(1536,520)
    view.add_child(renderer)
    var a: Dictionary = fixture["assets"]
    assert(renderer.set_verovio_glyphs(a["native_glyphs"], a["native_note_templates"],
        a["native_tie_templates"], a["native_chord_templates"], a["native_beam_fragments"],
        a["native_tuplet_fragments"], a["native_slur_fragments"],
        a["native_required_slur_pairs"], a["native_slurs_complete"],
        a["native_required_beam_groups"], a["native_beams_complete"]))
    var model: Dictionary = fixture["model"]
    var frames: Array = []
    frames.append(await _frame(view,renderer,model,.125,"start"))
    frames.append(await _frame(view,renderer,model,.375,"scroll"))
    renderer.load_score(model)
    await _capture(view,renderer,"editor-before.png")
    if renderer.has_signal("fingering_change_requested"):
        renderer.fingering_change_requested.connect(func(source_id: String, finger: Variant):
            requests.append({"source_id":source_id,"finger":finger}))
        var ids: Array = fixture["shared"]
        var click: Vector2 = renderer.drawn_noteheads[ids[0]]
        var event := InputEventMouseButton.new()
        event.button_index = MOUSE_BUTTON_RIGHT
        event.pressed = true
        event.position = click
        renderer._gui_input(event)
        if renderer.fingering_popup == null or not renderer.fingering_popup.visible:
            checks.append("Right click must open the correction popup")
        else:
            var menus: Array = []
            for child in renderer.fingering_popup.get_children():
                if child is PopupMenu:
                    menus.append(child)
            if menus.size() != 2:
                checks.append("Shared physical keys need independently editable source identities")
            else:
                menus[0].id_pressed.emit(5)
                menus[1].id_pressed.emit(0)
        renderer.fingering_popup.hide()
        var touch := InputEventScreenTouch.new()
        touch.pressed = true
        touch.position = click
        renderer._gui_input(touch)
        if not renderer.fingering_popup.visible:
            checks.append("Tap must open the correction popup")
        renderer.load_score(model)
        if renderer.fingering_popup.visible:
            checks.append("A changed score must dismiss stale editor targets")
        var unknown: Dictionary = model.duplicate(true)
        for note in unknown["notation_events"]:
            if note["id"] == fixture["unknown_id"]:
                note.erase("fingering")
        renderer.load_score(unknown)
        await _capture(view,renderer,"unknown.png")
        touch.position = renderer.drawn_noteheads[fixture["unknown_id"]]
        renderer._gui_input(touch)
        if not renderer.fingering_popup.visible:
            checks.append("Unknown attack heads must remain editable")
        else:
            renderer.fingering_popup.id_pressed.emit(3)
    else:
        checks.append("No fingering editor signal")
    var corrected: Dictionary = model.duplicate(true)
    var corrected_keys: Dictionary = {}
    for event in corrected["notation_events"]:
        if event["id"] == fixture["shared"][0]:
            event["fingering"]["finger"] = 5
            event["fingering"]["origin"] = "manual"
        if event.get("is_attack",false) and event.get("fingering") is Dictionary:
            corrected_keys[str(event["beat"])+"|"+str(event["staff"])+"|"+str(event["midi_pitch"])+"|"+str(event["fingering"]["finger"])] = true
    frames.append(await _frame(view,renderer,corrected,.125,"corrected"))
    renderer.size.y = 210
    frames.append(await _frame(view,renderer,model,.125,"compact"))
    renderer.size.y = 520
    var malformed: Dictionary = model.duplicate(true)
    var invalid: Array = [null,{}, {"finger":0}, {"finger":6}, {"finger":2.5},
        {"finger":true}, {"finger":"3"}, {"finger":2,"hand":"other","source_id":"x"}]
    var n := 0
    for event in malformed["notation_events"]:
        event["fingering"] = invalid[n % invalid.size()]
        n += 1
    renderer.load_score(malformed)
    renderer.present({"running":true,"paused":true,"hand":"both"},0.0)
    await _capture(view,renderer,"malformed.png")
    var bad: Image = view.get_texture().get_image()
    renderer.show_fingerings = false
    await _capture(view,renderer,"malformed-base.png")
    var base: Image = view.get_texture().get_image()
    var report := {"frames":frames,"density":renderer.timeline.pixels_per_beat,
        "editor_checks":checks,"requests":requests,"corrected_count":corrected_keys.size(),
        "malformed_matches_base":bad.get_data() == base.get_data()}
    # Independent text atlas at each cell's fractional raster phase. All five
    # possibilities are drawn; Python chooses the expected SOURCE assignment.
    var font: Font = ThemeDB.fallback_font
    var font_size := 16
    var references: Array = []
    for f in range(frames.size()):
        for i in range(frames[f]["labels"].size()):
            var label: Dictionary = frames[f]["labels"][i]
            var rect: Array = label["rect"]
            var width: int = ceili(float(rect[0])+float(rect[2]))-floori(float(rect[0]))
            var height: int = ceili(float(rect[1])+float(rect[3]))-floori(float(rect[1]))
            var phase := Vector2(float(rect[0])-floorf(float(rect[0])),float(rect[1])-floorf(float(rect[1])))
            var color: Color = renderer._ink(label["hand"])
            if label["hand"] == "left":
                color = color.lerp(renderer.Design.BLUE,.32)
            var reference := SubViewport.new()
            reference.size = Vector2i(width*5,height)
            reference.render_target_update_mode = SubViewport.UPDATE_ALWAYS
            root.add_child(reference)
            var canvas := Control.new()
            reference.add_child(canvas)
            canvas.draw.connect(func():
                for digit in range(1,6):
                    canvas.draw_string(font,phase+Vector2((digit-1)*width,font.get_ascent(font_size)),str(digit),
                        HORIZONTAL_ALIGNMENT_LEFT,-1,font_size,color))
            canvas.queue_redraw()
            label["reference"] = "digits-%d-%d.png" % [f,i]
            references.append({"view":reference,"file":label["reference"]})
    await process_frame
    await RenderingServer.frame_post_draw
    for reference in references:
        reference["view"].get_texture().get_image().save_png(folder.path_join(reference["file"]))
        reference["view"].queue_free()
    var file := FileAccess.open(folder.path_join("report.json"),FileAccess.WRITE)
    file.store_string(JSON.stringify(report))
    quit()
