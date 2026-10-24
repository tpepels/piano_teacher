extends SceneTree
# Actual native framebuffer probes. Only the extra-head intervention adds ink;
# all ordinary notation and deliberately wrong templates use the production view.

class Probe extends "res://notation/native/view.gd":
    var extra_head := false

    func _draw() -> void:
        super._draw()
        if extra_head and native_ready:
            glyphs.paint(self, "head_black", size.x*.42+_gap()*2.0,
                _staff_center("right"), _gap(), Color("e5f2ea"), true)

func _initialize() -> void:
    call_deferred("capture")

func capture() -> void:
    var args := OS.get_cmdline_user_args()
    var cases: Array = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
    var viewport := SubViewport.new()
    viewport.size = Vector2i(1536, 520)
    viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
    root.add_child(viewport)
    for item in cases:
        var renderer := Probe.new()
        renderer.size = Vector2(1536, 520)
        renderer.extra_head = bool(item.get("extra_head", false))
        viewport.add_child(renderer)
        var a: Dictionary = item["layout"]
        if not renderer.set_verovio_glyphs(a["native_glyphs"],
                a["native_note_templates"], a["native_tie_templates"],
                a["native_chord_templates"], a["native_beam_fragments"],
                a["native_tuplet_fragments"], a["native_slur_fragments"],
                a["native_required_slur_pairs"], a["native_slurs_complete"],
                a["native_required_beam_groups"], a["native_beams_complete"]) or \
                not renderer.load_score(item["model"]):
            push_error(renderer.failure_reason)
            quit(1)
            return
        renderer.present({"running":true, "paused":true, "bpm":40.0,
            "hand":"right", "transport_id":19, "count_in_beats":0.0,
            "play_from_beat":0.0}, 0.0)
        await process_frame
        await process_frame
        await RenderingServer.frame_post_draw
        var folder: String = args[1].path_join(item["name"])
        DirAccess.make_dir_recursive_absolute(folder)
        var image := viewport.get_texture().get_image()
        if image.is_empty() or image.save_png(folder.path_join("native-0.00000.png")) != OK:
            push_error("Cannot capture " + folder)
            quit(1)
            return
        renderer.queue_free()
        await process_frame
    print("NATIVE_HEAD_INK_CAPTURES:", cases.size())
    quit(0)
