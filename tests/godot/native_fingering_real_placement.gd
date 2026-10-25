extends "native_fingering.gd"

func _run() -> void:
    var args := OS.get_cmdline_user_args()
    folder = args[1]
    var fixture: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
    var viewport := SubViewport.new()
    viewport.size = Vector2i(2048,620)
    viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
    root.add_child(viewport)
    var renderer = load("res://notation/native/view.gd").new()
    renderer.size = Vector2(2048,620)
    viewport.add_child(renderer)
    var assets: Dictionary = fixture["assets"]
    assert(renderer.set_verovio_glyphs(assets["native_glyphs"],assets["native_note_templates"],
        assets["native_tie_templates"],assets["native_chord_templates"],assets["native_beam_fragments"],
        assets["native_tuplet_fragments"],assets["native_slur_fragments"],assets["native_required_slur_pairs"],
        assets["native_slurs_complete"],assets["native_required_beam_groups"],assets["native_beams_complete"]))
    var frames: Array = []
    frames.append(await _frame(viewport,renderer,fixture["model"],.125,"normal"))
    frames.append(await _frame(viewport,renderer,fixture["model"],.375,"scroll"))
    var density: float = renderer.timeline.pixels_per_beat
    renderer.set_transport_overlay_enabled(true)
    renderer.present({"running":true,"paused":true,"hand":"both"},.125)
    await _capture(viewport,renderer,"after.png")
    renderer.set_fingering_annotations_enabled(false)
    await _capture(viewport,renderer,"after-canonical.png")
    renderer.set_fingering_annotations_enabled(true)
    # Before evidence uses the committed compositor against the SAME real
    # model, source glyph assets, camera and viewport. It is not a mock view.
    if fixture.has("before_script"):
        renderer.queue_free()
        await process_frame
        var previous = load(fixture["before_script"]).new()
        previous.size = Vector2(2048,620)
        viewport.add_child(previous)
        assert(previous.set_verovio_glyphs(assets["native_glyphs"],assets["native_note_templates"],
            assets["native_tie_templates"],assets["native_chord_templates"],assets["native_beam_fragments"],
            assets["native_tuplet_fragments"],assets["native_slur_fragments"],assets["native_required_slur_pairs"],
            assets["native_slurs_complete"],assets["native_required_beam_groups"],assets["native_beams_complete"]))
        previous.load_score(fixture["model"])
        previous.present({"running":true,"paused":true,"hand":"both"},.125)
        await _capture(viewport,previous,"before.png")
    # The reference font and hand colours are public APIs, independent of
    # renderer placement. A temporary node supplies only the same hand ink.
    var reference_renderer = load("res://notation/native/view.gd").new()
    reference_renderer.active_hand = "both"
    await _digit_references(frames,reference_renderer)
    reference_renderer.free()
    var file := FileAccess.open(folder.path_join("report.json"),FileAccess.WRITE)
    file.store_string(JSON.stringify({"frames":frames,"density":density}))
    quit()
