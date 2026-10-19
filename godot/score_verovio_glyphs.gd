extends RefCounted
# Authenticated Verovio Leipzig / Bravura font artwork, drawn by Godot.
#
# This class deliberately does NOT generate SVG, music glyph paths, fonts or
# score pages. The Python engine exports each *single glyph* from Verovio's
# installed font resources, including precise origin and bounds. Godot
# imports it once as a cached ImageTexture and composes/scrolls the score
# natively using ScoreTimeline. No rendered page is moved or sliced here.

const REQUIRED := [
    "clef_g", "clef_f", "clef_c",
    "head_whole", "head_half", "head_black", "augmentation_dot",
    "rest_whole", "rest_half", "rest_quarter", "rest_eighth",
    "rest_16th", "rest_32nd", "rest_64th",
    "acc_flat", "acc_natural", "acc_sharp",
    "acc_double_sharp", "acc_double_flat",
    "flag_up_1", "flag_down_1", "flag_up_2", "flag_down_2",
    "flag_up_3", "flag_down_3", "flag_up_4", "flag_down_4",
    "time_0", "time_1", "time_2", "time_3", "time_4",
    "time_5", "time_6", "time_7", "time_8", "time_9",
]
const RASTER_SCALE := 1.75
# Noteheads, stems and flags rendered together by Verovio, not assembled
# from native primitives at draw time. Beamed/chorded groups remain structural.
const NOTE_TEMPLATES := [
    "whole", "half_up", "half_down",
    "quarter_up", "quarter_down",
    "eighth_up", "eighth_down",
    "16th_up", "16th_down",
    "32nd_up", "32nd_down",
    "64th_up", "64th_down",
]

var textures: Dictionary = {}
var bounds: Dictionary = {}
var font_name := ""
var note_textures: Dictionary = {}
var note_bounds: Dictionary = {}
var error := ""

func ready() -> bool:
    return textures.size() == REQUIRED.size()

func load_font(items: Dictionary) -> bool:
    if ready():
        return true
    var loaded_textures: Dictionary = {}
    var loaded_bounds: Dictionary = {}
    var common_font := ""
    for name in REQUIRED:
        var entry: Dictionary = items.get(name, {})
        if str(entry.get("source", "")) != "verovio":
            error = "Missing authentic Verovio glyph: " + name
            return false
        if int(entry.get("units_per_space", 0)) != 250:
            error = "Incorrect Verovio staff-scale for " + name
            return false
        var source_font: String = str(entry.get("font", ""))
        if source_font.is_empty() or (not common_font.is_empty() and common_font != source_font):
            error = "Mixed or unknown Verovio fonts"
            return false
        common_font = source_font
        var geometry: Array = entry.get("bounds", [])
        if geometry.size() != 4 or float(geometry[2]) <= 0.0 or float(geometry[3]) <= 0.0:
            error = "Invalid engraved glyph bounds for " + name
            return false
        var svg: String = str(entry.get("svg", ""))
        if not svg.contains("<svg") or not svg.contains("<path"):
            error = "Missing original font outline for " + name
            return false
        var image := Image.new()
        if image.load_svg_from_buffer(svg.to_utf8_buffer(), RASTER_SCALE) != OK:
            error = "Godot cannot rasterize Verovio symbol " + name
            return false
        if image.is_empty():
            error = "Empty Verovio symbol " + name
            return false
        loaded_textures[name] = ImageTexture.create_from_image(image)
        loaded_bounds[name] = geometry.duplicate()
    textures = loaded_textures
    bounds = loaded_bounds
    font_name = common_font
    error = ""
    return true

func note_ready() -> bool:
    return note_textures.size() == NOTE_TEMPLATES.size()


func load_note_templates(items: Dictionary) -> bool:
    if note_ready():
        return true
    var new_textures: Dictionary = {}
    var new_bounds: Dictionary = {}
    for name in NOTE_TEMPLATES:
        var item: Dictionary = items.get(name, {})
        if str(item.get("source", "")) != "verovio-engraved-note" or \
                int(item.get("units_per_space", 0)) != 250:
            error = "Missing Verovio-engraved complete note " + name
            return false
        var coordinates: Array = item.get("bounds", [])
        if coordinates.size() != 4 or float(coordinates[2]) <= 0.0 or \
                float(coordinates[3]) <= 0.0:
            error = "Invalid Verovio note dimensions: " + name
            return false
        var encoded: String = str(item.get("png_base64", ""))
        if encoded.is_empty():
            error = "Missing Verovio note image: " + name
            return false
        var bytes: PackedByteArray = Marshalls.base64_to_raw(encoded)
        var note := Image.new()
        if note.load_png_from_buffer(bytes) != OK or note.is_empty():
            error = "Invalid authentic Verovio note image: " + name
            return false
        new_textures[name] = ImageTexture.create_from_image(note)
        new_bounds[name] = coordinates.duplicate()
    note_textures = new_textures
    note_bounds = new_bounds
    error = ""
    return true


func paint_note(canvas: CanvasItem, kind: String, up: bool,
        x: float, y: float, gap: float, ink: Color) -> bool:
    var name: String = ("whole" if kind == "whole"
        else kind + ("_up" if up else "_down"))
    var texture: Texture2D = note_textures.get(name)
    if texture == null:
        return false
    var box: Array = note_bounds[name]
    canvas.draw_texture_rect(texture,
        Rect2(x+float(box[0])*gap/250.0,
            y+float(box[1])*gap/250.0,
            float(box[2])*gap/250.0,
            float(box[3])*gap/250.0), false, ink)
    return true


# x,y are a glyph's musical anchor, not the top-left of a page.
# A font-space unit is 1/250 of the current staff-space (line-to-line gap).
# The graphics below do not adjust musical X or the transport clock.
func paint(canvas: CanvasItem, name: String, x: float, y: float,
        space_px: float, color: Color,
        centered_x: bool = false) -> bool:
    var glyph: Texture2D = textures.get(name)
    if glyph == null:
        return false
    var box: Array = bounds[name]
    var unit: float = space_px / 250.0
    var shift_x: float = (float(box[0]) + float(box[2]) * .5) if centered_x else 0.0
    var rect := Rect2(
        x + (float(box[0]) - shift_x) * unit,
        y + float(box[1]) * unit,
        float(box[2]) * unit, float(box[3]) * unit
    )
    canvas.draw_texture_rect(glyph, rect, false, color)
    return true
