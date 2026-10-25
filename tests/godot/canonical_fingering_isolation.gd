extends SceneTree
# Exercise the public production switch on the real compositor, including
# reloads and scrolling. There is no screenshot mask or substitute renderer.
var folder: String

func _initialize() -> void:
    call_deferred("_run")

func _capture(view: SubViewport, renderer: Control, name: String) -> void:
    renderer.queue_redraw()
    await process_frame
    await process_frame
    await RenderingServer.frame_post_draw
    assert(view.get_texture().get_image().save_png(folder.path_join(name)) == OK)

func _run() -> void:
    var args := OS.get_cmdline_user_args()
    folder = args[1]
    var fixture: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
    var viewport := SubViewport.new()
    viewport.size = Vector2i(1536,520)
    viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
    root.add_child(viewport)
    var renderer = load("res://notation/native/view.gd").new()
    renderer.size = Vector2(1536,520)
    viewport.add_child(renderer)
    assert(renderer.fingering_annotations_enabled, "Ordinary application must show fingerings by default")
    var a: Dictionary = fixture["assets"]
    assert(renderer.set_verovio_glyphs(a["native_glyphs"], a["native_note_templates"],
        a["native_tie_templates"], a["native_chord_templates"], a["native_beam_fragments"],
        a["native_tuplet_fragments"], a["native_slur_fragments"],
        a["native_required_slur_pairs"], a["native_slurs_complete"],
        a["native_required_beam_groups"], a["native_beams_complete"]))
    var original: Dictionary = fixture["model"]
    var changed: Dictionary = original.duplicate(true)
    var removed: Dictionary = original.duplicate(true)
    for event in changed["notation_events"]:
        if event.get("fingering") is Dictionary:
            event["fingering"]["finger"] = 5
    for event in removed["notation_events"]:
        event.erase("fingering")
    var frames: Array = []
    var editor_checks: Array = []
    var references: Array = []
    for index in range(2):
        # Keep instructional OCR cells clear of the fixed playhead graphic.
        var clock := .125+float(index)*.25
        var frame := {"labels":[]}
        for variant in [{"name":"original","model":original},
                {"name":"changed","model":changed},{"name":"removed","model":removed}]:
            assert(renderer.load_score(variant["model"]), renderer.failure_reason)
            renderer.present({"running":true,"paused":true,"bpm":40.0,"hand":"both",
                "transport_id":19,"count_in_beats":0.0,"play_from_beat":0.0},clock)
            renderer.set_fingering_annotations_enabled(true)
            var normal := "normal-%d-%s.png" % [index,variant["name"]]
            await _capture(viewport,renderer,normal)
            if variant["name"] == "original":
                frame["file"] = normal
                for item in renderer.drawn_fingerings:
                    var rect: Rect2 = item["rect"]
                    var head: Vector2 = item["head"]
                    var ink_rect: Rect2 = item.get("ink_rect",rect)
                    frame["labels"].append({"rect":[rect.position.x,rect.position.y,rect.size.x,rect.size.y],
                        "head":[head.x,head.y],"finger":item["finger"],"hand":item["hand"],
                        "ink_rect":[ink_rect.position.x,ink_rect.position.y,ink_rect.size.x,ink_rect.size.y],
                        "font_size":item.get("font_size",16),"text_offset_x":item.get("text_offset_x",0.0),
                        "orientation":item.get("orientation","above" if item["hand"] == "right" else "below"),
                        "event_ids":item["event_ids"]})
                frame["gap"] = renderer._gap()
                frame["placement_issues"] = renderer.fingering_placement_issues.duplicate(true)
            else:
                frame["normal_"+variant["name"]] = normal
            renderer.set_fingering_annotations_enabled(false)
            if not renderer.drawn_fingerings.is_empty():
                editor_checks.append("Disabling annotations must clear stale label targets immediately")
            if renderer._open_fingering_editor(renderer.drawn_noteheads.values()[0]):
                editor_checks.append("Canonical mode must not edit hidden annotations")
            var canonical := "canonical-%d-%s.png" % [index,variant["name"]]
            await _capture(viewport,renderer,canonical)
            assert(renderer.drawn_fingerings.is_empty())
            frame["canonical" if variant["name"] == "original" else "canonical_"+variant["name"]] = canonical
        frames.append(frame)
    # Hide a genuine written note only after load validation, leaving the
    # source XML, staff, atlas and every other musical event unchanged.
    assert(renderer.load_score(original))
    renderer.present({"running":true,"paused":true,"bpm":40.0,"hand":"both",
        "transport_id":19,"count_in_beats":0.0,"play_from_beat":0.0},0.0)
    var kept: Array = []
    var missing_id := ""
    for event in renderer.ordered_events:
        if missing_id.is_empty() and event["kind"] == "note" and event["staff"] == "right":
            missing_id = str(event["id"])
        else:
            kept.append(event)
    renderer.ordered_events = kept
    await _capture(viewport,renderer,"missing-musical-note.png")
    # Independent all-digit reference atlas for the existing strict OCR oracle.
    var font: Font = ThemeDB.fallback_font
    for f in range(frames.size()):
        for i in range(frames[f]["labels"].size()):
            var label: Dictionary = frames[f]["labels"][i]
            var font_size: int = int(label["font_size"])
            var rect: Array = label["rect"]
            var width := ceili(float(rect[0])+float(rect[2]))-floori(float(rect[0]))
            var height := ceili(float(rect[1])+float(rect[3]))-floori(float(rect[1]))
            var phase := Vector2(float(rect[0])-floorf(float(rect[0]))+float(label["text_offset_x"]),
                float(rect[1])-floorf(float(rect[1])))
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
                canvas.draw_rect(Rect2(Vector2.ZERO,Vector2(width*5,height)),renderer.Design.STAGE)
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
    var output := FileAccess.open(folder.path_join("isolation-report.json"),FileAccess.WRITE)
    output.store_string(JSON.stringify({"frames":frames,"editor_checks":editor_checks,
        "missing_note":"missing-musical-note.png","missing_id":missing_id}))
    quit()
