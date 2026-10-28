extends SceneTree

func _initialize() -> void:
    var fixture: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(OS.get_cmdline_user_args()[0]))
    var view = load("res://notation/native/view.gd").new()
    view.size = Vector2(1536,520)
    root.add_child(view)
    var a: Dictionary = fixture["assets"]
    assert(view.set_verovio_glyphs(a["native_glyphs"],a["native_note_templates"],
        a["native_tie_templates"],a["native_chord_templates"],a["native_beam_fragments"],
        a["native_tuplet_fragments"],a["native_slur_fragments"],a["native_required_slur_pairs"],
        a["native_slurs_complete"],a["native_required_beam_groups"],a["native_beams_complete"]))
    assert(view.load_score(fixture["model"]))
    var gap := 22.0
    var heads: Dictionary = view.layout.engraved_head_offsets(gap)
    var shifted: Dictionary = heads.duplicate()
    for event in view.layout.ordered_events:
        if str(event.get("kind","")) == "note":
            var id: String = str(event["id"])
            shifted[id] = float(heads.get(id,0.0))+17.0
    var checked := 0
    for event in view.layout.ordered_events:
        if str(event.get("kind","")) != "note":
            continue
        var original: Rect2 = view.layout.event_ink_rect(event,gap,heads,{})
        var moved: Rect2 = view.layout.event_ink_rect(event,gap,shifted,{})
        if absf(moved.position.x-original.position.x-17.0) > .001 or \
                absf(moved.end.x-original.end.x-17.0) > .001:
            push_error("Voice sprite bounds must translate with every head/stem: "+str(event["id"]))
            quit(1)
            return
        checked += 1
    assert(checked > 0)
    print("VOICE_SPRITE_BOUNDS:",checked)
    quit(0)
