extends SceneTree
# Real backend payloads and authentic Verovio assets, never synthetic atlases.
const Native := preload("res://notation/native/view.gd")

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    if OS.get_environment("PIANO_TEACHER_NATIVE_NOTATION") != "1":
        push_error("Native notation must be explicitly selected")
        quit(1)
        return
    var args := OS.get_cmdline_user_args()
    var payload: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
    var layout: Dictionary = payload["layout"]
    var renderer = Native.new()
    root.add_child(renderer)
    renderer.size = Vector2(1536, 700)
    var loaded: bool = renderer.set_verovio_glyphs(
        layout.get("native_glyphs", {}), layout.get("native_note_templates", {}),
        layout.get("native_tie_templates", {}), layout.get("native_chord_templates", {}),
        layout.get("native_beam_fragments", {}), layout.get("native_tuplet_fragments", {}),
        layout.get("native_slur_fragments", {}), layout.get("native_required_slur_pairs", []),
        layout.get("native_slurs_complete", false), layout.get("native_required_beam_groups", []),
        layout.get("native_beams_complete", false))
    loaded = loaded and renderer.load_score(payload["model"])
    var drawn_ids: Dictionary = {}
    var expected_ids: Dictionary = {}
    var linear := loaded
    var density: float = renderer.timeline.pixels_per_beat
    if loaded:
        # Advance to each still-unseen onset. One viewport usually verifies
        # several attacks; sparse measure-start snapshots miss dense passages.
        for event in renderer.layout.ordered_events:
            if str(event.get("kind","")) == "note":
                expected_ids[str(event["id"])] = true
        for event in renderer.layout.ordered_events:
            if str(event.get("kind","")) != "note" or drawn_ids.has(str(event["id"])):
                continue
            var beat: float = float(event["beat"])
            renderer.present({"bpm":80, "running":true, "paused":false,
                "count_in_beats":0, "play_from_beat":0, "hand":"both",
                "transport_id":1}, beat)
            renderer.queue_redraw()
            await process_frame
            await process_frame
            for id in renderer.drawn_noteheads:
                drawn_ids[str(id)] = true
            var x0: float = renderer.timeline.screen_x(beat, beat, 500, 0)
            var x1: float = renderer.timeline.screen_x(beat + .25, beat, 500, 0)
            linear = linear and absf(x1 - x0 - density * .25) < .001
            linear = linear and renderer.timeline.pixels_per_beat == density
    var missing: Array = []
    for id in expected_ids:
        if not drawn_ids.has(id):
            missing.append(id)
    var report := {"native_ready":loaded and renderer.native_ready,
        "reason":renderer.failure_reason, "drawn_noteheads":drawn_ids.size(),
        "expected_noteheads":expected_ids.size(), "missing_noteheads":missing,
        "linear_timeline":linear, "pixels_per_beat":density}
    var file := FileAccess.open(args[1], FileAccess.WRITE)
    file.store_string(JSON.stringify(report))
    file.close()
    renderer.free()
    quit(0 if loaded and linear and drawn_ids.size() > 0 and missing.is_empty() else 1)
