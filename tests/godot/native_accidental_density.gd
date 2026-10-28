extends SceneTree

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
        OS.get_cmdline_user_args()[0]))
    var renderer = load("res://notation/native/view.gd").new()
    root.add_child(renderer)
    renderer.size = Vector2(1200,560)
    if OS.get_environment("PIANO_TEACHER_NATIVE_NOTATION") != "1" or not \
            renderer.set_verovio_glyphs(data["glyphs"],data["notes"],data["ties"],
                data["chords"],{}) or not renderer.load_score(data["model"]):
        print("NATIVE_ACCIDENTAL_DENSITY_FAIL: Authentic native fixture did not load")
        quit(1)
        return
    var density: float = renderer.timeline.pixels_per_beat
    var failures := 0
    if bool(data.get("vertically_separated",false)):
        if absf(density-96.0) > .001:
            failures += 1
            print("NATIVE_ACCIDENTAL_DENSITY_FAIL: Vertically clear voices expanded density to ",density)
        print("NATIVE_ACCIDENTAL_DENSITY_FAILURES:",failures)
        quit(0 if failures == 0 else 1)
        return
    for height in [360.0,560.0,900.0]:
        renderer.size.y = height
        renderer.queue_redraw()
        await process_frame
        await process_frame
        var gap: float = renderer.staff_gap()
        var box: Array = renderer.glyphs.bounds["acc_sharp"]
        var first_right: float = (float(renderer.glyphs.note_bounds["quarter_up"][0])+ \
            float(renderer.glyphs.note_bounds["quarter_up"][2]))*gap/250.0
        var next_left := INF
        for event in data["model"]["notation_events"]:
            if not str(event["id"]).begins_with("sharp_"):
                continue
            var id: String = str(event["id"])
            var left: float = density+float(renderer.layout.cached_head_offsets.get(id,0.0))+ \
                float(renderer.layout.cached_accidental_offsets[id])-float(box[2])*gap/500.0
            next_left = minf(next_left,left)
        if next_left < first_right+gap*.2-.001:
            failures += 1
            print("NATIVE_ACCIDENTAL_DENSITY_FAIL: Packed ink starts at ",next_left,
                " before preceding note ends at ",first_right," at height ",height)
        if renderer.timeline.pixels_per_beat != density or \
                absf(renderer.timeline.x_at_beat(1.0)-density) > .001 or \
                renderer.timeline.model["notation_events"] != data["model"]["notation_events"]:
            failures += 1
            print("NATIVE_ACCIDENTAL_DENSITY_FAIL: Source timing or fixed scale changed")
    print("NATIVE_ACCIDENTAL_DENSITY_FAILURES:",failures)
    quit(0 if failures == 0 else 1)
