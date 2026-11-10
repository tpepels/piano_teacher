extends SceneTree

func _compile(renderer) -> void:
    var deadline := Time.get_ticks_msec()+8000
    while not renderer.retained_ready() and Time.get_ticks_msec() < deadline:
        renderer.queue_redraw()
        await process_frame

func _settle_stream(renderer, state: Dictionary) -> void:
    # The frame coordinator (present_flow) attaches compiled strips to their
    # presentation clips; this harness has no backend frames.
    var deadline := Time.get_ticks_msec()+8000
    while Time.get_ticks_msec() < deadline:
        renderer.stream_world_beat = 1.0
        renderer.present_flow(1.0,state,0.0,false)
        await process_frame
        var attached: bool = not renderer._stream_queue.online.is_empty()
        for strip in renderer._stream_queue.online:
            if strip.get("segment") == null or strip["segment"].get_parent() != strip["clip"]:
                attached = false
        if attached:
            break

func _capture(viewport: SubViewport, renderer, path: String) -> void:
    renderer.queue_redraw()
    await process_frame
    await process_frame
    await RenderingServer.frame_post_draw
    viewport.get_texture().get_image().save_png(path)

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
        # READY/paused frames paint no source ink (perpetual score stream). Admit one
        # source take into the stream exactly as the verovio overlay audit does.
        var state := {"running":false,"paused":true,"hand":"right",
            "count_in_beats":0.0,"play_from_beat":0.0}
        renderer.present(state,0.0)
        await _compile(renderer)
        renderer.stream_world_beat = -40.0
        renderer._stream_add_take(0.0,0.0,0.0,"singleton-probe")
        await _settle_stream(renderer,state)
        await _capture(viewport,renderer,args[1].path_join("with-tuplet.png"))
        renderer.glyphs.tuplet_textures.clear()
        # Retained ink is cached in child CanvasItems: re-record it so the
        # removed artwork is actually absent from the second capture.
        renderer._invalidate_retained_segments()
        await _settle_stream(renderer,state)
        await _capture(viewport,renderer,args[1].path_join("without-tuplet.png"))
    else:
        renderer.glyphs.tuplet_textures.clear()
    if renderer.load_score(data["model"]):
        push_error("A visible singleton with missing artwork was silently accepted")
        quit(1)
        return
    print("NATIVE_SINGLETON_TUPLET_CHECKED:1")
    quit(0)
