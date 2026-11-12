extends SceneTree
## Print the side each tie of a prepared score bows to in the native view.
## Args: <input.json> with {layout, model}.

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var item: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
        OS.get_cmdline_user_args()[0]))
    var view = load("res://notation/native/view.gd").new()
    view.size = Vector2(1600, 560)
    root.add_child(view)
    var a: Dictionary = item["layout"]
    if not view.set_verovio_glyphs(a["native_glyphs"], a["native_note_templates"],
            a["native_tie_templates"], a["native_chord_templates"], a["native_beam_fragments"],
            a["native_tuplet_fragments"], a["native_slur_fragments"],
            a["native_required_slur_pairs"], a["native_slurs_complete"],
            a["native_required_beam_groups"], a["native_beams_complete"]) or \
            not view.load_score(item["model"]):
        print("TIE_SIDES_FAILED:", view.failure_reason)
        quit(1)
        return
    var gap: float = view.staff_gap()
    var sides: Dictionary = {}
    for pair in view.layout.tie_pairs:
        sides[str(pair["first"]["id"])] = "below" if \
            view.connector_geometry.tie_bow_down(pair["first"], pair["last"], gap) else "above"
    print("TIE_SIDES:", JSON.stringify(sides))
    quit(0)
