extends SceneTree
## G1 chord probe: load each imported exercise in the production native view,
## show every chord at the playhead and report where each of its heads was
## painted, which template drew it, or why the score refused to load.
## Args: <input.json> <output.json> [capture folder]. With a capture folder
## the view renders into a real viewport and saves one PNG per chord.
const FramebufferTake := preload("framebuffer_take.gd")

## The stem as painted, relative to the leader's head centre in staff spaces:
## side (up), centre-line offset (dx) and the far end (tip). A beamed chord's
## stem comes from the beam plan; any other chord's from its template sprite.
func _stem(renderer, leader: Dictionary, key: String, beat: float, gap: float) -> Dictionary:
    var box: Array = renderer.glyphs.chord_stem_bounds.get(key, [])
    if box.size() != 4:
        return {}
    var id: String = str(leader.get("id", ""))
    var dx: float = (float(box[0])+float(box[2])*.5)/250.0
    if renderer.layout.beamed_note_ids.has(id):
        var plan: Dictionary = renderer.beam_plan(gap, beat, renderer.size.x*.33,
            renderer.layout.cached_head_offsets)
        if not plan["stems"].has(id):
            return {"beamed": true, "missing": true}
        var stem: Dictionary = plan["stems"][id]
        return {"beamed": true, "up": bool(stem["up"]), "dx": dx,
            "tip": (float(stem["tip_y"])-renderer.layout.event_y(leader, gap))/gap}
    # Side read from the painted geometry, not from the template's own
    # direction: a stem whose centre lies above the heads' centre rises.
    var top := INF
    var bottom := -INF
    for position in renderer.glyphs.chord_heads(key):
        top = minf(top, float(position[1]))
        bottom = maxf(bottom, float(position[1]))
    var up: bool = float(box[1])+float(box[3])*.5 < (top+bottom)*.5
    return {"beamed": false, "up": up, "dx": dx,
        "tip": (float(box[1]) if up else float(box[1])+float(box[3]))/250.0}

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
        # As in the practice stage, whose progress rail runs along the bottom.
        renderer.layout.bottom_clearance = renderer.PROGRESS_RAIL_CLEARANCE
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
                var gap: float = renderer.staff_gap()
                var entry := {"key": key, "has_template": renderer.glyphs.has_chord(key),
                    "gap": gap, "heads": heads, "sources": sources,
                    "stem": _stem(renderer, by_id[leader], key, float(chord["beat"]), gap)}
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
