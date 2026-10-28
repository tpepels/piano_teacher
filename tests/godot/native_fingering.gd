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

func _frame(view: SubViewport, renderer: Control, model: Dictionary, clock: float, name: String,
        virtual_clock: float = NAN, tempo: float = 60.0) -> Dictionary:
    renderer.load_score(model)
    renderer.set_transport_overlay_enabled(false)
    renderer.set_fingering_annotations_enabled(true)
    renderer.present({"running":true, "paused":true, "hand":"both","bpm":tempo,
        "score_loop_enabled":is_finite(virtual_clock)}, clock, virtual_clock)
    await _capture(view, renderer, name+".png")
    var labels: Array = []
    var noteheads: Dictionary = {}
    for id in renderer.drawn_noteheads:
        var point: Vector2 = renderer.drawn_noteheads[id]
        noteheads[id] = [point.x,point.y]
    if renderer.annotations.drawn_fingerings is Array:
        for item in renderer.annotations.drawn_fingerings:
            var rect: Rect2 = item["rect"]
            var head: Vector2 = item["head"]
            labels.append({"rect":[rect.position.x,rect.position.y,rect.size.x,rect.size.y],
                "head":[head.x,head.y], "finger":item["finger"], "hand":item["hand"],
                "font_size":item.get("font_size",16),"text_offset_x":item.get("text_offset_x",0.0),
                "orientation":item.get("orientation","above" if item["hand"] == "right" else "below"),
                "event_ids":item["event_ids"]})
    var placement_issues: Array = renderer.annotations.fingering_placement_issues.duplicate(true)
    renderer.set_fingering_annotations_enabled(false)
    await _capture(view, renderer, name+"-base.png")
    renderer.set_fingering_annotations_enabled(true)
    return {"file":name+".png", "base":name+"-base.png", "labels":labels,"gap":renderer.staff_gap(),
        "placement_issues":placement_issues,"noteheads":noteheads,
        "capture_config":{"fingering_annotations":true,"transport_overlay":false}}

func _run() -> void:
    var args := OS.get_cmdline_user_args()
    folder = args[1]
    var fixture: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
    var view := SubViewport.new()
    view.size = Vector2i(1536,520)
    view.render_target_update_mode = SubViewport.UPDATE_ALWAYS
    root.add_child(view)
    var renderer = load("res://notation/native/view.gd").new()
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
        if renderer.annotations.fingering_popup == null or not renderer.annotations.fingering_popup.visible:
            checks.append("Right click must open the correction popup")
        else:
            var menus: Array = []
            for child in renderer.annotations.fingering_popup.get_children():
                if child is PopupMenu:
                    menus.append(child)
            if menus.size() != 2:
                checks.append("Shared physical keys need independently editable source identities")
            else:
                menus[0].id_pressed.emit(5)
                menus[1].id_pressed.emit(0)
        renderer.annotations.fingering_popup.hide()
        var touch := InputEventScreenTouch.new()
        touch.pressed = true
        touch.position = click
        renderer._gui_input(touch)
        if not renderer.annotations.fingering_popup.visible:
            checks.append("Tap must open the correction popup")
        renderer.load_score(model)
        if renderer.annotations.fingering_popup.visible:
            checks.append("A changed score must dismiss stale editor targets")
        var unknown: Dictionary = model.duplicate(true)
        for note in unknown["notation_events"]:
            if note["id"] == fixture["unknown_id"]:
                note.erase("fingering")
        renderer.load_score(unknown)
        await _capture(view,renderer,"unknown.png")
        touch.position = renderer.drawn_noteheads[fixture["unknown_id"]]
        renderer._gui_input(touch)
        if not renderer.annotations.fingering_popup.visible:
            checks.append("Unknown attack heads must remain editable")
        else:
            renderer.annotations.fingering_popup.id_pressed.emit(3)
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
    renderer.size.y = 400
    frames.append(await _frame(view,renderer,model,.125,"compact"))
    renderer.size.y = 210
    frames.append(await _frame(view,renderer,model,.125,"insufficient-space"))
    renderer.size.y = 520
    var last_measure: Dictionary = renderer.timeline.measures[-1]
    var stride: float = renderer.timeline.duration_beats+float(last_measure["end_beat"])-float(last_measure["start_beat"])
    frames.append(await _frame(view,renderer,model,.125,"loop",stride+.125))
    frames.append(await _frame(view,renderer,model,.125,"tempo",NAN,125.0))
    var authored: Dictionary = model.duplicate(true)
    var authored_ids: Array = []
    for event in authored["notation_events"]:
        if event.get("fingering") is Dictionary and event["staff"] == "left" and float(event["beat"]) == 0.0:
            event["fingering"]["placement"] = {"placement":"above"}
            authored_ids.append(event["id"])
    frames.append(await _frame(view,renderer,authored,.125,"authored"))
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
    renderer.set_fingering_annotations_enabled(false)
    await _capture(view,renderer,"malformed-base.png")
    var base: Image = view.get_texture().get_image()
    var report := {"frames":frames,"density":renderer.timeline.pixels_per_beat,
        "authored_ids":authored_ids,
        "authored_horizontal_hint":_authored_horizontal_hint(),
        "envelope_coverage":_envelope_coverage(renderer),
        "editor_checks":checks,"requests":requests,"corrected_count":corrected_keys.size(),
        "malformed_matches_base":bad.get_data() == base.get_data()}
    await _digit_references(frames,renderer)
    var file := FileAccess.open(folder.path_join("report.json"),FileAccess.WRITE)
    file.store_string(JSON.stringify(report))
    quit()


func _authored_horizontal_hint() -> bool:
    var policy = load("res://notation/native/fingering_placement.gd")
    var ordinary: Array = policy.candidates(Vector2(200,100),Vector2(8,12),20.0,-1.0,false,true,200.0)
    var authored: Array = policy.candidates(Vector2(200,100),Vector2(8,12),20.0,-1.0,false,true,200.0,{"default_x":4.0})
    return not ordinary.is_empty() and not authored.is_empty() and \
        authored[0]["position"].is_equal_approx(ordinary[0]["position"]+Vector2(8,0))


func _envelope_coverage(renderer: Control) -> Dictionary:
    var checked := 0
    var uncovered := 0
    var corrupted_uncovered := 0
    var templates: Array = []
    for key in renderer.glyphs.note_textures:
        if key == "whole":
            continue
        templates.append({"key":key,"chord":"","kind":str(key).get_slice("_",0),
            "up":str(key).ends_with("_up"),"texture":renderer.glyphs.note_textures[key],
            "bounds":renderer.glyphs.note_bounds[key],"heads":[[0.0,0.0]]})
    for key in renderer.glyphs.chord_textures:
        var metadata: Dictionary = renderer.glyphs.chord_metadata[key]
        templates.append({"key":key,"chord":key,"kind":str(key).get_slice("|",0),
            "up":str(key).get_slice("|",1) == "up","texture":renderer.glyphs.chord_textures[key],
            "bounds":metadata["bounds"],"heads":metadata["head_positions"]})
    for template in templates:
        var envelope: Rect2 = renderer.annotations.obstacles.nonhead_envelope(template["kind"],template["up"],template["chord"])
        var picture: Image = template["texture"].get_image()
        var box: Array = template["bounds"]
        var shape: Array = renderer.glyphs.bounds["head_"+(template["kind"] if template["kind"] in ["whole","half"] else "black")]
        for y in range(picture.get_height()):
            for x in range(picture.get_width()):
                if picture.get_pixel(x,y).a == 0.0:
                    continue
                checked += 1
                var point := Vector2(float(box[0])+(x+.5)*float(box[2])/picture.get_width(),
                    float(box[1])+(y+.5)*float(box[3])/picture.get_height())
                var head_pixel := false
                for center in template["heads"]:
                    if Rect2(float(center[0])-float(shape[2])*.5,float(center[1])+float(shape[1]),
                            float(shape[2]),float(shape[3])).has_point(point):
                        head_pixel = true
                if not head_pixel:
                    if not envelope.grow(.001).has_point(point):
                        uncovered += 1
                    # Deliberately erase the non-head envelope. The authentic
                    # shaft/flag pixels must expose this corrupted reservation.
                    corrupted_uncovered += 1
    return {"pixels":checked,"uncovered":uncovered,"corrupted_uncovered":corrupted_uncovered,
        "templates":templates.size()}


func _digit_references(frames: Array, renderer: Control) -> void:
    # Independent text atlas at each cell's fractional raster phase. All five
    # possibilities are drawn; Python chooses the expected SOURCE assignment.
    var font: Font = ThemeDB.fallback_font
    var references: Array = []
    for f in range(frames.size()):
        for i in range(frames[f]["labels"].size()):
            var label: Dictionary = frames[f]["labels"][i]
            var font_size: int = int(label["font_size"])
            var text_offset: float = float(label["text_offset_x"])
            var rect: Array = label["rect"]
            var width: int = ceili(float(rect[0])+float(rect[2]))-floori(float(rect[0]))
            var height: int = ceili(float(rect[1])+float(rect[3]))-floori(float(rect[1]))
            var phase := Vector2(float(rect[0])-floorf(float(rect[0])),float(rect[1])-floorf(float(rect[1])))
            var color: Color = renderer.RenderPass.new({"active_hand":renderer.active_hand}).ink(label["hand"])
            if label["hand"] == "left":
                color = color.lerp(renderer.Design.BLUE,.32)
            var reference := SubViewport.new()
            reference.size = Vector2i(width*5,height)
            reference.render_target_update_mode = SubViewport.UPDATE_ALWAYS
            root.add_child(reference)
            var canvas := Control.new()
            reference.add_child(canvas)
            canvas.draw.connect(func():
                canvas.draw_rect(Rect2(Vector2.ZERO,Vector2(width*5,height)),renderer.Design.STAGE)
                for digit in range(1,6):
                    canvas.draw_string(font,phase+Vector2((digit-1)*width+text_offset,font.get_ascent(font_size)),str(digit),
                        HORIZONTAL_ALIGNMENT_LEFT,-1,font_size,color))
            canvas.queue_redraw()
            label["reference"] = "digits-%d-%d.png" % [f,i]
            references.append({"view":reference,"file":label["reference"]})
    await process_frame
    await RenderingServer.frame_post_draw
    for reference in references:
        reference["view"].get_texture().get_image().save_png(folder.path_join(reference["file"]))
        reference["view"].queue_free()
