extends RefCounted

const FOREST := Color("#0E191C")
const PINE := Color("#204840")
const PANEL := Color("#1A2C2C")
const SAGE := Color("#5C8F7E")
const SLATE := Color("#ADC4B8")
const STONE := Color("#E1EEE5")
const TEAL := Color("#7BE8C0")

static func surface(color: Color, radius: int = 8) -> StyleBoxFlat:
    var box := StyleBoxFlat.new()
    box.bg_color = color
    box.set_corner_radius_all(radius)
    box.set_content_margin_all(12)
    return box

static func create() -> Theme:
    var theme := Theme.new()
    var font := SystemFont.new()
    font.font_names = PackedStringArray(["Inter", "Noto Sans", "DejaVu Sans"])
    theme.default_font = font
    theme.default_font_size = 15
    for control in ["Label", "Button", "LineEdit", "SpinBox", "CheckButton", "OptionButton", "PopupMenu"]:
        theme.set_color("font_color", control, STONE)
        theme.set_color("font_hover_color", control, STONE.lightened(.15))
        theme.set_color("font_focus_color", control, STONE)
        theme.set_color("font_pressed_color", control, STONE)
        theme.set_color("font_disabled_color", control, SLATE)
    theme.set_color("font_placeholder_color", "LineEdit", SLATE)
    theme.set_color("caret_color", "LineEdit", TEAL)
    for control in ["LineEdit", "SpinBox", "OptionButton", "PopupMenu"]:
        theme.set_stylebox("normal", control, surface(PANEL))
        theme.set_stylebox("panel", control, surface(PANEL))
        theme.set_stylebox("hover", control, surface(PINE))
        theme.set_stylebox("pressed", control, surface(PINE))
        var focus := surface(Color.TRANSPARENT)
        focus.set_border_width_all(2)
        focus.border_color = TEAL
        theme.set_stylebox("focus", control, focus)
    theme.set_stylebox("scroll", "VScrollBar", surface(FOREST, 3))
    theme.set_stylebox("grabber", "VScrollBar", surface(SAGE, 3))
    theme.set_stylebox("grabber_highlight", "VScrollBar", surface(SLATE, 3))
    return theme

static func notation_material() -> ShaderMaterial:
    var shader := Shader.new()
    shader.code = """shader_type canvas_item;
render_mode unshaded;
void fragment() {
    vec4 sample_color = texture(TEXTURE, UV);
    float ink = 1.0 - dot(sample_color.rgb, vec3(0.2126, 0.7152, 0.0722));
    COLOR = vec4(vec3(0.883, 0.928, 0.891), sample_color.a * ink);
}
"""
    var material := ShaderMaterial.new()
    material.shader = shader
    return material
