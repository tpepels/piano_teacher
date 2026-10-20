extends SceneTree

var failures: Array[String] = []

func check(ok: bool, label: String) -> void:
    if not ok:
        failures.append(label)
        print("NATIVE_BEAMED_CHORD_FAIL: ",label)

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    check(OS.get_environment("PIANO_TEACHER_NATIVE_NOTATION") == "1",
        "Authored regression explicitly selects native notation")
    var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
        OS.get_cmdline_user_args()[0]))
    var renderer = load("res://notation/native/view.gd").new()
    root.add_child(renderer)
    renderer.size = Vector2(1200,560)
    check(renderer.set_verovio_glyphs(data["glyphs"],data["notes"],
        data["ties"],data["chords"],data["beams"],{},{},[],true,
        ["a|b","c|d"],true),"All assets come from real Verovio engraving")
    check(renderer.load_score(data["model"]) and renderer.native_ready,
        "Both opposite-direction beamed chords load without fallback")
    var by_id: Dictionary = {}
    for event in data["model"]["notation_events"]:
        by_id[str(event["id"])] = event
    check(renderer._chord_template_key(by_id["a"]) == "eighth|down|0,2",
        "Low chord forced DOWN uses the original left-side stem and head displacement")
    check(renderer._chord_template_key(by_id["c"]) == "eighth|up|0,2",
        "High chord forced UP uses the original right-side stem and head displacement")
    var painted: Dictionary = {}
    var density: float = renderer.timeline.pixels_per_beat
    for beat in [0.0,4.0]:
        renderer.present({"running":true,"bpm":80,"hand":"both"},beat)
        renderer.queue_redraw()
        await process_frame
        await process_frame
        for id in renderer.drawn_noteheads:
            painted[id] = true
        var gap: float = renderer._gap()
        var beams: Dictionary = renderer._beam_layout(gap,beat,1200.0*.42,
            renderer.cached_head_offsets)
        var id: String = "a" if beat == 0.0 else "c"
        var up: bool = beat != 0.0
        check(beams["stems"].has(id) and bool(beams["stems"][id]["up"]) == up,
            "Stem direction and chord key agree with the original authored beam")
        var key: String = "eighth|up|0,2" if up else "eighth|down|0,2"
        var stem_box: Array = renderer.glyphs.chord_stem_bounds[key]
        var stem_x: float = renderer.timeline.screen_x(beat,beat,1200.0*.42)+ \
            (float(stem_box[0])+float(stem_box[2])*.5)*gap/250.0
        check(absf(float(beams["stems"][id]["x"])-stem_x) < 2.0,
            "Native beam attaches to the original sprite's correct stem side")
        check(absf(renderer.timeline.screen_x(beat+.5,beat,500.0)- \
            renderer.timeline.screen_x(beat,beat,500.0)-density*.5) < .001 and \
            renderer.timeline.pixels_per_beat == density,
            "Forced stem direction never changes the one global timing scale")
    check(painted.size() == 6,"Every original chord tone and single note is drawn")
    # Missing requested direction must fail validation, rather than paint a
    # source-opposite stem from an available isolated-chord template.
    var saved: Texture2D = renderer.glyphs.chord_textures["eighth|down|0,2"]
    renderer.glyphs.chord_textures.erase("eighth|down|0,2")
    check(not renderer.load_score(data["model"]) and not renderer.native_ready and
        renderer.failure_reason.contains("eighth|down|0,2"),
        "Validation requires the authoritative beam direction before drawing")
    renderer.glyphs.chord_textures["eighth|down|0,2"] = saved
    var isolated: Dictionary = data["model"].duplicate(true)
    check(renderer.glyphs.load_beam_fragments({}),"Clear old source beam atlas")
    renderer.expected_beam_groups.clear()
    check(renderer.load_score(isolated) and renderer.native_ready,
        "A following isolated-chord score loads after source beam cache replacement")
    check(renderer._chord_template_key(by_id["a"]) == "eighth|up|0,2" and
        renderer._chord_template_key(by_id["c"]) == "eighth|down|0,2",
        "Old beam directions never leak into the next lesson")
    print("NATIVE_BEAMED_CHORD_FAILURES:",failures.size())
    renderer.free()
    quit(0 if failures.is_empty() else 1)
