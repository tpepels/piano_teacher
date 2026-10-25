extends SceneTree
# Dedicated production-view capture only: no renderer geometry is exported.

func _initialize() -> void:
    call_deferred("capture")

func capture() -> void:
    var args := OS.get_cmdline_user_args()
    var fixture: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
    var viewport := SubViewport.new()
    viewport.size = Vector2i(1536,520)
    viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
    root.add_child(viewport)
    var renderer = load("res://notation/native/view.gd").new()
    renderer.size = Vector2(1536,520)
    viewport.add_child(renderer)
    var a: Dictionary = fixture["assets"]
    if not renderer.set_verovio_glyphs(a["native_glyphs"], a["native_note_templates"],
            a["native_tie_templates"], a["native_chord_templates"],
            a["native_beam_fragments"], a["native_tuplet_fragments"],
            a["native_slur_fragments"], a["native_required_slur_pairs"],
            a["native_slurs_complete"], a["native_required_beam_groups"],
            a["native_beams_complete"]) or not renderer.load_score(fixture["model"]):
        push_error(renderer.failure_reason)
        quit(1)
        return
    for clock in [0.0, 1.0/3.0, 2.0/3.0, 1.0]:
        renderer.present({"running":true,"paused":true,"bpm":40.0,"hand":"right",
            "transport_id":19,"count_in_beats":0.0,"play_from_beat":0.0},clock)
        await process_frame
        await process_frame
        await RenderingServer.frame_post_draw
        var image := viewport.get_texture().get_image()
        if image.is_empty() or image.save_png(args[1].path_join("native-%.5f.png" % clock)) != OK:
            push_error("Cannot capture actual tuplet framebuffer")
            quit(1)
            return
    print("MOONLIGHT_TUPLET_CAPTURES:4")
    quit(0)
