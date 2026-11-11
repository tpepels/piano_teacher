extends SceneTree
## G1 chord probe: load each imported exercise in the production native view,
## show every chord at the playhead and report where each of its heads was
## painted, which template drew it, or why the score refused to load.
## Args: <input.json> <output.json> [capture folder]. With a capture folder
## the view renders into a real viewport and saves one PNG per chord.
const FramebufferTake := preload("framebuffer_take.gd")

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var args := OS.get_cmdline_user_args()
    var items: Array = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
    var capture: String = args[2] if args.size() > 2 else ""
    var viewport: SubViewport = null
    if not capture.is_empty():
        viewport = SubViewport.new()
        viewport.size = Vector2i(1600, 560)
        viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
        root.add_child(viewport)
    var results: Array = []
    for item in items:
        var renderer = load("res://notation/native/view.gd").new()
        renderer.size = Vector2(1600, 560)
        if viewport != null:
            viewport.add_child(renderer)
        else:
            root.add_child(renderer)
        renderer.set_transport_overlay_enabled(false)
        var a: Dictionary = item["layout"]
        var result := {"name": item["name"], "ready": false, "failure": "", "chords": {}}
        var glyphs_ok: bool = renderer.set_verovio_glyphs(a["native_glyphs"],
            a["native_note_templates"], a["native_tie_templates"],
            a["native_chord_templates"], a["native_beam_fragments"],
            a["native_tuplet_fragments"], a["native_slur_fragments"],
            a["native_required_slur_pairs"], a["native_slurs_complete"],
            a["native_required_beam_groups"], a["native_beams_complete"])
        var loaded: bool = glyphs_ok and renderer.load_score(item["model"])
        result["ready"] = loaded and renderer.native_ready
        result["failure"] = str(renderer.failure_reason)
        if result["ready"]:
            var by_id: Dictionary = {}
            for event in item["model"]["notation_events"]:
                by_id[str(event.get("id", ""))] = event
            for chord in item["chords"]:
                var leader: String = str(chord["leader"])
                var key: String = renderer.layout.chord_template_key(by_id[leader])
                await FramebufferTake.show(self, renderer, {"running": true, "paused": true,
                    "bpm": 40.0, "hand": "both", "transport_id": 7,
                    "count_in_beats": 0.0, "play_from_beat": 0.0}, float(chord["beat"]))
                await process_frame
                var heads: Dictionary = {}
                for id in chord["members"]:
                    if renderer.drawn_noteheads.has(str(id)):
                        var point: Vector2 = renderer.drawn_noteheads[str(id)]
                        heads[str(id)] = [point.x, point.y]
                var sources: Dictionary = {}
                for instance in renderer.drawn_note_instances:
                    var id: String = str(instance.get("event_id", ""))
                    if id in chord["members"]:
                        sources[id] = [str(instance.get("source", "")),
                            str(instance.get("template", "")), int(instance.get("head_index", -1))]
                var entry := {"key": key, "has_template": renderer.glyphs.has_chord(key),
                    "gap": renderer.staff_gap(), "heads": heads, "sources": sources}
                if viewport != null and bool(chord.get("capture", false)):
                    await RenderingServer.frame_post_draw
                    var image := viewport.get_texture().get_image()
                    var path: String = capture.path_join("%s-%s.png" % [item["name"], leader])
                    entry["png"] = path if not image.is_empty() and image.save_png(path) == OK else ""
                result["chords"][leader] = entry
        results.append(result)
        renderer.queue_free()
        await process_frame
    var out := FileAccess.open(args[1], FileAccess.WRITE)
    out.store_string(JSON.stringify(results))
    out.close()
    print("CHORD_ENGRAVING_PROBE_ITEMS:", results.size())
    quit(0)
