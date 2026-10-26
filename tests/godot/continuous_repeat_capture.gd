extends "native_fingering.gd"

func _run() -> void:
    var args := OS.get_cmdline_user_args()
    folder = args[1]
    var fixture: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
    var viewport := SubViewport.new()
    viewport.size = Vector2i(1536,520)
    viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
    root.add_child(viewport)
    var renderer = load("res://notation/native/view.gd").new()
    renderer.size = Vector2(1536,520)
    viewport.add_child(renderer)
    var a: Dictionary = fixture["assets"]
    assert(renderer.set_verovio_glyphs(a["native_glyphs"],a["native_note_templates"],
        a["native_tie_templates"],a["native_chord_templates"],a["native_beam_fragments"],
        a["native_tuplet_fragments"],a["native_slur_fragments"],a["native_required_slur_pairs"],
        a["native_slurs_complete"],a["native_required_beam_groups"],a["native_beams_complete"]))
    assert(renderer.load_score(fixture["model"]),renderer.failure_reason)
    # Public fixed density makes the quarter-beat distance a test input;
    # independent PNG translation still verifies its actual projection.
    assert(renderer.set_density(96.0))
    var frames: Array = []
    for sample in fixture["repeat_frames"]:
        var state: Dictionary = fixture.get("state",{}).duplicate(true)
        state.merge({"running":true,"paused":true,"hand":fixture.get("hand","both"),
            "bpm":60.0,"play_from_beat":0.0,"score_loop_enabled":true,
            "visual_gap_beats":fixture["gap_beats"]},true)
        state.merge(sample.get("state",{}),true)
        state["paused"] = true
        var clock: float = float(sample["clock"])
        renderer.set_transport_overlay_enabled(false)
        renderer.set_fingering_annotations_enabled(true)
        renderer.present(state,clock,clock)
        var tag: String = sample["name"]
        await _capture(viewport,renderer,tag+".png")
        var labels: Array = []
        for item in renderer.drawn_fingerings:
            var rect: Rect2 = item["rect"]
            var head: Vector2 = item["head"]
            labels.append({"rect":[rect.position.x,rect.position.y,rect.size.x,rect.size.y],
                "head":[head.x,head.y],"finger":item["finger"],"hand":item["hand"],
                "font_size":item["font_size"],"text_offset_x":item["text_offset_x"],
                "orientation":item["orientation"],"event_ids":item["event_ids"],
                "pass_index":item.get("pass_index",-1)})
        var instances: Array = []
        var observed: Variant = renderer.get("drawn_note_instances")
        if observed is Array:
            for item in observed:
                var point: Vector2 = item["position"]
                instances.append({"source_id":item["source_id"],"event_id":item["event_id"],
                    "pass_index":item["pass_index"],"position":[point.x,point.y]})
        renderer.set_fingering_annotations_enabled(false)
        await _capture(viewport,renderer,tag+"-canonical.png")
        frames.append({"name":tag,"clock":clock,"file":tag+".png","base":tag+"-canonical.png",
            "gap":renderer._gap(),"labels":labels,"instances":instances})
    renderer.set_fingering_annotations_enabled(true)
    await _capture(viewport,renderer,"interaction-ready.png")
    var interactions: Array = []
    renderer.fingering_change_requested.connect(func(source_id: String, finger: Variant):
        interactions.append({"source_id":source_id,"finger":finger}))
    var clicks: Array = []
    var groups: Dictionary = {}
    for item in renderer.drawn_fingerings:
        if item["hand"] != fixture.get("hand","both") and fixture.get("hand","both") != "both":
            continue
        var key: String = str(item["event_ids"])
        if not groups.has(key):
            groups[key] = []
        groups[key].append(item)
    for group in groups.values():
        if group.size()<2:
            continue
        for item in group.slice(0,2):
            var expected: String = renderer._fingering_source(renderer.expression_note_index[item["event_ids"][0]])
            var point: Vector2 = item["head"]
            var opened: bool = renderer._open_fingering_editor(point)
            clicks.append({"expected_source_id":expected,"pass_index":item.get("pass_index",-1),"opened":opened})
            if opened:
                renderer.fingering_popup.id_pressed.emit(5)
                renderer.fingering_popup.hide()
        break
    var evidence_state: Dictionary = fixture.get("state",{}).duplicate(true)
    evidence_state.merge({"running":true,"paused":true,"hand":fixture.get("hand","both"),
        "score_loop_enabled":true,"visual_gap_beats":fixture["gap_beats"],"play_from_beat":0.0},true)
    var rest_clock: float = float(fixture["model"]["duration_beats"])+float(fixture["gap_beats"])*.5
    renderer.set_transport_overlay_enabled(true)
    renderer.present(evidence_state,rest_clock,rest_clock)
    await _capture(viewport,renderer,"evidence-rest.png")
    await _digit_references(frames,renderer)
    var file := FileAccess.open(folder.path_join("repeat-report.json"),FileAccess.WRITE)
    file.store_string(JSON.stringify({"frames":frames,"density_input":96.0,
        "clicks":clicks,"interactions":interactions}))
    quit()
