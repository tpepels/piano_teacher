extends SceneTree

func _initialize() -> void:
    call_deferred("_check")

func _check() -> void:
    var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(OS.get_cmdline_user_args()[0]))
    var assets: Dictionary = data["assets"]
    var renderer = load("res://notation/native/view.gd").new()
    renderer.size = Vector2(1536,520)
    root.add_child(renderer)
    if not renderer.set_verovio_glyphs(assets["native_glyphs"], assets["native_note_templates"],
            assets["native_tie_templates"], assets["native_chord_templates"],
            assets["native_beam_fragments"], assets["native_tuplet_fragments"],
            assets["native_slur_fragments"], assets["native_required_slur_pairs"],
            assets["native_slurs_complete"], assets["native_required_beam_groups"],
            assets["native_beams_complete"]) or not renderer.load_score(data["model"]):
        print("REST_LANE_LOAD_FAILED:",renderer.failure_reason)
        quit(1)
        return
    var failures := 0
    var checked := 0
    for event in renderer.layout.ordered_events:
        if str(event.get("kind","")) == "rest" and str(event.get("note_type","")) in ["half","whole"]:
            checked += 1
            var offset: float = float(renderer.layout.rest_lane_offsets.get(str(event["id"]),0.0))
            if absf(offset-roundf(offset)) > .00001:
                print("RECTANGULAR_REST_OFF_GRID:",event["id"]," shift=",offset)
                failures += 1
    print("RECTANGULAR_RESTS_CHECKED:",checked)
    quit(0 if failures == 0 and checked > 0 else 1)
