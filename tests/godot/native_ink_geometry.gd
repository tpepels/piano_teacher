extends SceneTree
const Layout := preload("res://notation/native/score_layout.gd")
const Ink := preload("res://notation/native/ink_geometry.gd")
const Axis := preload("res://notation/shared/timeline.gd")
const Glyphs := preload("res://notation/native/glyphs.gd")

func _initialize() -> void:
    var path := "res://../tests/fixtures/hanon_boundary_clearance/fixture.json"
    var fixture: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))
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
    layout.layout_rest_lanes(22,96)
    var ink := Ink.new(layout)
    var first: Dictionary = ink.minimum_density(96,22)
    var second: Dictionary = ink.minimum_density(96,22)
    var failures := 0
    if absf(float(first["density"])-286.785905456543)>.001:
        failures += 1
    if first["witness"].get("reason")!="outgoing-barline-clearance":
        failures += 1
    if first!=second or axis.model!=source:
        failures += 1
    if ink.texture_bands.is_empty():
        failures += 1
    ink.clear_cache()
    if not ink.texture_bands.is_empty():
        failures += 1
    print("INK_GEOMETRY_FAILURES:",failures)
    quit(0 if failures==0 else 1)
