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

var textures: Dictionary = {}
var bounds: Dictionary = {}
var font_name := ""
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
