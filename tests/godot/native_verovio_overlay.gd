extends SceneTree
# Render the same native view.gd used in Practice, from real score model and
# authentic Verovio atlas. Export anchor metadata for machine-checked
# Verovio/native comparison; this is NOT the retired ScoreStrip renderer.
var failures: Array[String] = []

func _initialize() -> void:
    call_deferred("_audit")

func _audit() -> void:
    var args: PackedStringArray = OS.get_cmdline_user_args()
    if args.size() != 2:
        push_error("Usage: -- FIXTURE_JSON OUTPUT_DIR")
        quit(2)
        return
    var fixture: Variant = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
    if not fixture is Dictionary:
        push_error("Invalid native overlay fixture")
        quit(2)
        return
    var folder: String = args[1]
    DirAccess.make_dir_recursive_absolute(folder)
    var view := SubViewport.new()
    view.size = Vector2i(1536, 520)
    view.transparent_bg = false
    view.render_target_update_mode = SubViewport.UPDATE_ALWAYS
    root.add_child(view)
    var renderer = load("res://notation/native/view.gd").new()
    renderer.size = Vector2(1536, 520)
    view.add_child(renderer)
    var assets: Dictionary = fixture["assets"]
    if not renderer.set_verovio_glyphs(
            assets["native_glyphs"], assets["native_note_templates"],
            assets["native_tie_templates"], assets["native_chord_templates"],
            assets["native_beam_fragments"], assets["native_tuplet_fragments"],
            assets["native_slur_fragments"], assets["native_required_slur_pairs"],
            assets["native_slurs_complete"], assets["native_required_beam_groups"],
            assets["native_beams_complete"]):
        push_error("Authentic Verovio asset load failed: " + renderer.failure_reason)
        quit(1)
        return
    if not renderer.load_score(fixture["model"]):
        push_error("Native source-backed layout rejected: " + renderer.failure_reason)
        quit(1)
        return
    var result := {
        "density": renderer.timeline.pixels_per_beat,
        "density_witness": renderer.selected_density_witness.duplicate(true),
        "staff_gap": renderer._gap(),
        "width": renderer.size.x,
        "height": renderer.size.y,
        "staff_centers": {
            "right": renderer._staff_center("right"),
            "left": renderer._staff_center("left")
        },
        "unavoidable_rest_overlaps": renderer.unavoidable_rest_overlaps,
        "frames": [],
    }
    var samples: Array = fixture.get("sample_beats", [0.0, 1.5, 3.5, 5.5])
    for point in samples:
        var at: float = float(point)
        renderer.present({
            "running": true, "paused": true,
            "bpm": 40.0, "hand": str(fixture.get("hand","both")),
            "transport_id": 19, "count_in_beats": 0.0,
            "play_from_beat": 0.0
        }, at)
        await process_frame
        await process_frame
        await RenderingServer.frame_post_draw
        var frame: Image = view.get_texture().get_image()
        # Quarter-note subdivisions can be closer than .01 beats. Use
        # precise filenames in Phase 3 to prevent one frame overwriting
        # another; preserve Phase 2's existing artifact names.
        var filename: String = ("native-%.5f.png" if bool(fixture.get(
            "phase3_full",false)) else "native-%.2f.png") % at
        if frame.is_empty() or frame.save_png(folder.path_join(filename)) != OK:
            failures.append("Cannot capture " + filename)
        var heads: Dictionary = {}
        for identifier in renderer.drawn_noteheads:
            var xy: Vector2 = renderer.drawn_noteheads[identifier]
            heads[str(identifier)] = [xy.x, xy.y]
        var rests: Array = []
        var camera_x: float = renderer.size.x*.42
        var expected_heads: Dictionary = {}
        for event in renderer.ordered_events:
            if str(event.get("kind", "")) != "note":
                continue
            var expected_x: float = renderer.timeline.screen_x(
                float(event.get("beat", 0.0)),at,camera_x)
            if expected_x > 20.0 and expected_x < renderer.size.x-20.0:
                expected_heads[str(event.get("id", ""))] = expected_x
        for event in renderer.ordered_events:
            if str(event.get("kind","")) != "rest":
                continue
            var x: float = renderer.timeline.screen_x(float(event["beat"]),at,camera_x)
            if x < 0.0 or x > renderer.size.x:
                continue
            rests.append({
                "id": event["id"], "x": x,
                "y": renderer._rest_y(event,renderer._gap()),
                "type": event["note_type"], "dots": event["dots"],
                "hand": event["staff"],
            })
        result["frames"].append({
            "clock": at, "file": filename,
            "noteheads": heads, "expected_noteheads": expected_heads,
            "rests": rests,
            "visible_symbols": renderer.visible_symbols
        })
    print("NATIVE_DENSITY_DIAGNOSTIC:", str(fixture.get("first_bar", 0)),
        "-", str(fixture.get("last_bar", 0)), " ",
        JSON.stringify(result["density_witness"]))
    var output := FileAccess.open(folder.path_join("native-overlay-report.json"),FileAccess.WRITE)
    if output == null:
        failures.append("Cannot save native audit metadata")
    else:
        output.store_string(JSON.stringify(result,"  ")+"\n")
        output.close()
    print("NATIVE_VEROVIO_OVERLAY_FAILURES:", failures.size())
    for failure in failures:
        push_error(failure)
    quit(0 if failures.is_empty() else 1)
