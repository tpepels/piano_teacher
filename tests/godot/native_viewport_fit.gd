extends SceneTree
const Layout := preload("res://notation/native/score_layout.gd")
const Ink := preload("res://notation/native/ink_geometry.gd")
const Fit := preload("res://notation/native/viewport_fit.gd")
const Axis := preload("res://notation/shared/timeline.gd")
const Glyphs := preload("res://notation/native/glyphs.gd")

func _initialize() -> void:
    var fixture: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
        "res://../tests/fixtures/hanon_boundary_clearance/fixture.json"))
    var assets: Dictionary = fixture["assets"]
    var glyphs := Glyphs.new()
    assert(glyphs.load_font(assets["native_glyphs"]))
    assert(glyphs.load_note_templates(assets["native_note_templates"]))
    assert(glyphs.load_chord_templates(assets["native_chord_templates"]))
    assert(glyphs.load_beam_fragments(assets["native_beam_fragments"]))
    var axis := Axis.new()
    assert(axis.load_model(fixture["model"]))
    var source := axis.model.duplicate(true)
    var layout := Layout.new(axis,glyphs)
    layout.set_viewport(Vector2(1536,520))
    layout.rebuild_index()
    var ink := Ink.new(layout)
    var fit: Dictionary = Fit.choose(layout,ink,96,.42)
    var failures := 0
    if not fit["ok"] or absf(float(fit["density"])-286.785905456543)>.001 or fit["staff_gap"]!=22.0:
        failures += 1
    if axis.pixels_per_beat!=96.0 or axis.model!=source:
        failures += 1
    var large: float = layout.staff_gap(22)
    var small: float = layout.staff_gap(14)
    if large<=14.0 or small>14.0:
        failures += 1
    var invalid: Dictionary = Fit.choose(layout,ink,9000,.42)
    if invalid["ok"] or invalid["error"].is_empty():
        failures += 1
    print("VIEWPORT_FIT_FAILURES:",failures)
    quit(0 if failures==0 else 1)
