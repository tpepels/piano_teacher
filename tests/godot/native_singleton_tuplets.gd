extends SceneTree

func _initialize() -> void:
    call_deferred("_check")

func _check() -> void:
    var args := OS.get_cmdline_user_args()
    var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
    var assets: Dictionary = data["assets"]
    var viewport := SubViewport.new()
    viewport.size = Vector2i(1536,520)
    viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
    root.add_child(viewport)
    var renderer = load("res://notation/native/view.gd").new()
    renderer.size = Vector2(1536,520)
    viewport.add_child(renderer)
    if not renderer.set_verovio_glyphs(assets["native_glyphs"], assets["native_note_templates"],
            assets["native_tie_templates"], assets["native_chord_templates"],
            assets["native_beam_fragments"], assets["native_tuplet_fragments"],
            assets["native_slur_fragments"], assets["native_required_slur_pairs"],
            assets["native_slurs_complete"], assets["native_required_beam_groups"],
            assets["native_beams_complete"]) or not renderer.load_score(data["model"]):
        push_error(renderer.failure_reason)
        quit(1)
        return
    var visible := 0
    for group in renderer.layout.notation_tuplets:
        if str(group.get("show_number","actual")) == "none" and str(group.get("bracket","yes")) == "no":
            continue
        if group["events"].size() != 1:
            push_error("Expected the exact singleton source boundary")
            quit(1)
            return
        var identifier: String = str(group["events"][0]["id"])
        if not renderer.glyphs.has_tuplet(identifier,true):
            push_error("Missing independently engraved singleton artwork")
            quit(1)
            return
        visible += 1
    if visible != 1:
        push_error("Expected one visible source singleton")
        quit(1)
        return
    if args.size() > 1:
        renderer.present({"running":false,"paused":true,"hand":"right",
            "count_in_beats":0.0,"play_from_beat":0.0},0.0)
        await process_frame
        await process_frame
        await RenderingServer.frame_post_draw
        viewport.get_texture().get_image().save_png(args[1].path_join("with-tuplet.png"))
    renderer.glyphs.tuplet_textures.clear()
    if args.size() > 1:
        renderer.queue_redraw()
        await process_frame
        await process_frame
        await RenderingServer.frame_post_draw
        viewport.get_texture().get_image().save_png(args[1].path_join("without-tuplet.png"))
    if renderer.load_score(data["model"]):
        push_error("A visible singleton with missing artwork was silently accepted")
        quit(1)
        return
    print("NATIVE_SINGLETON_TUPLET_CHECKED:1")
    quit(0)
