extends "native_fingering.gd"

func _renderer(viewport: SubViewport, assets: Dictionary, script_path: String, dimensions: Vector2):
    var renderer = load(script_path).new()
    renderer.size = dimensions
    viewport.add_child(renderer)
    assert(renderer.set_verovio_glyphs(assets["native_glyphs"],assets["native_note_templates"],
        assets["native_tie_templates"],assets["native_chord_templates"],assets["native_beam_fragments"],
        assets["native_tuplet_fragments"],assets["native_slur_fragments"],assets["native_required_slur_pairs"],
        assets["native_slurs_complete"],assets["native_required_beam_groups"],assets["native_beams_complete"]))
    return renderer

func _local_witnesses(renderer: Control) -> Array:
    var found: Array = []
    var gap: float = renderer.staff_gap()
    var font_size: int = clampi(roundi(gap*.75),11,16)
    var metrics: Dictionary = renderer.annotations.metrics(font_size)
    var ink: Vector2 = metrics["ink_size"]
    var cell: float = maxf(64.0,renderer.timeline.pixels_per_beat)
    var bins: Dictionary = {}
    var picture: Image = renderer.get_viewport().get_texture().get_image()
    var background: Color = picture.get_pixel(0,0)
    var translation := Vector2(renderer.timeline.screen_x(0.0,.125,renderer.size.x*.42,renderer.play_from_beat),0.0)
    renderer.annotations.obstacles.build(gap,bins,cell,renderer.play_from_beat)
    for placed in renderer.annotations.fingering_layout:
        renderer.annotations.obstacles.block(placed["ink_rect"],bins,cell)
    for issue in renderer.annotations.fingering_placement_issues:
        var event: Dictionary = renderer.layout.expression_note_index[issue["event_ids"][0]]
        var head := Vector2(float(event["beat"])*renderer.timeline.pixels_per_beat+
            float(renderer.layout.cached_head_offsets.get(str(event["id"]),0.0)),renderer.layout.event_y(event,gap))
        var witness: Dictionary = {}
        for dy in range(-24,25):
            for dx in range(-20,21):
                var offset := Vector2(dx,dy)*gap*.1
                if offset.length()>gap*2.45 or offset.length()<gap*.7:
                    continue
                var rect := Rect2(head+offset-ink*.5,ink)
                var text_rect := Rect2(rect.position-metrics["ink_offset"],metrics["cell"])
                if text_rect.position.y<0.0 or text_rect.end.y>renderer.size.y:
                    continue
                if renderer.annotations.obstacles.is_clear(rect,bins,cell) and _pixel_box_clear(rect,translation,picture,background):
                    witness = {"source_id":issue["source_id"],"head":[head.x,head.y],
                        "ink_rect":[rect.position.x,rect.position.y,rect.size.x,rect.size.y],
                        "offset":[offset.x/gap,offset.y/gap]}
                    break
            if not witness.is_empty():
                break
        if not witness.is_empty():
            found.append(witness)
    return found

func _pixel_box_clear(rect: Rect2, translation: Vector2, picture: Image, background: Color) -> bool:
    rect.position += translation
    for y in range(floori(rect.position.y)-2,ceili(rect.end.y)+2):
        for x in range(floori(rect.position.x)-2,ceili(rect.end.x)+2):
            if x<0 or y<0 or x>=picture.get_width() or y>=picture.get_height():
                return false
            var pixel: Color = picture.get_pixel(x,y)
            if maxf(absf(pixel.r-background.r),maxf(absf(pixel.g-background.g),absf(pixel.b-background.b)))>.03:
                return false
    return true

func _run() -> void:
    var args := OS.get_cmdline_user_args()
    folder = args[1]
    var fixture: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
    var dimensions := Vector2(float(fixture["size"][0]),float(fixture["size"][1]))
    var viewport := SubViewport.new()
    viewport.size = Vector2i(dimensions)
    viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
    root.add_child(viewport)
    var renderer = _renderer(viewport,fixture["assets"],"res://notation/native/view.gd",dimensions)
    var frames: Array = []
    frames.append(await _frame(viewport,renderer,fixture["model"],.125,"normal"))
    var without_punctuation: Dictionary = fixture["model"].duplicate(true)
    for measure in without_punctuation["measures"]:
        measure["left_barline"] = {"style":"none","repeat":""}
        measure["right_barline"] = {"style":"none","repeat":""}
    renderer.load_score(without_punctuation)
    renderer.set_fingering_annotations_enabled(false)
    await _capture(viewport,renderer,"punctuation-free.png")
    renderer.load_score(fixture["model"])
    renderer.set_fingering_annotations_enabled(true)
    # _frame toggles annotation mode after its baseline; rebuild before probes.
    await _capture(viewport,renderer,"diagnostic.png")
    var witnesses: Array = _local_witnesses(renderer)
    var envelope: Dictionary = _envelope_coverage(renderer)
    var app = load("res://main.gd").new()
    app.practice_view.stage.renderer = renderer
    app.layout_revision = app.revision
    app.timeline_model_revision = app.revision
    app.rendered_revision = app.revision
    app.practice_view.stage.fingering_status_label = Label.new()
    app._present_fingering_status(fixture["summary"])
    var warning := {"text":app.practice_view.stage.fingering_status_label.text,"tooltip":app.practice_view.stage.fingering_status_label.tooltip_text,
        "visible":app.practice_view.stage.fingering_status_label.visible}
    app.practice_view.stage.fingering_status_label.free()
    app.free()
    frames.append(await _frame(viewport,renderer,fixture["model"],.375,"scroll"))
    var regressed: Dictionary = {}
    if fixture.has("regressed_script"):
        renderer.queue_free()
        await process_frame
        renderer = _renderer(viewport,fixture["assets"],"res://notation/native/view.gd",dimensions)
        renderer.annotations.obstacles = load(fixture["regressed_script"]).new(renderer.layout,renderer.connector_geometry)
        regressed = await _frame(viewport,renderer,fixture["model"],.125,"regressed")
    var references: Array = frames.duplicate()
    if not regressed.is_empty():
        references.append(regressed)
    await _digit_references(references,renderer)
    var file := FileAccess.open(folder.path_join("report.json"),FileAccess.WRITE)
    file.store_string(JSON.stringify({"frames":frames,"regressed":regressed,"envelope":envelope,
        "warning":warning,"local_witnesses":witnesses,"punctuation_free":"punctuation-free.png"}))
    quit()
