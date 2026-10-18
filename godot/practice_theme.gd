extends RefCounted

# Piano Teacher visual system. Screens describe *meaning*, not their own
# independent colors or borders. Keep static drawing cheap on HiDPI displays.
const FOREST := Color("#0E191C")
const STAGE := Color("#F0F4E8")
const SCORE_INK := Color("#263D34")
const SCORE_MUTED := Color("#71857B")
const SCORE_ACCENT := Color("#83F1C6")
const SCORE_PROGRESS := Color("#82CBAA")
const PINE := Color("#204840")
const PANEL := Color("#1A2C2C")
const PANEL_RAISED := Color("#203634")
const PANEL_RECESSED := Color("#142626")
const SAGE := Color("#5C8F7E")
const SLATE := Color("#ADC4B8")
const STONE := Color("#E1EEE5")
const TEAL := Color("#7BE8C0")
const MINT := Color("#A5FFDB")
const BLUE := Color("#9DCAFF")
const AMBER := Color("#F2CB92")
const CORAL := Color("#FFA5A0")
const BORDER := Color("#658F81")
const FOCUS := Color("#EFFCF5")

# A consistent scale for cards, modal interiors and form layout.
const SPACE_TIGHT := 6
const SPACE_SMALL := 10
const SPACE_NORMAL := 16
const SPACE_SECTION := 24
const RADIUS_INPUT := 10
const RADIUS_CARD := 14
const RADIUS_MODAL := 18

static func font(weight: int = 400) -> SystemFont:
    var result := SystemFont.new()
    result.font_names = PackedStringArray(["Inter", "Noto Sans", "DejaVu Sans"])
    result.font_weight = weight
    return result

static func surface(color: Color, radius: int = RADIUS_INPUT) -> StyleBoxFlat:
    var box := StyleBoxFlat.new()
    box.bg_color = color
    box.set_corner_radius_all(radius)
    box.set_content_margin_all(12)
    return box

static func bordered_surface(color: Color, radius: int = RADIUS_CARD,
        border_alpha: float = .3) -> StyleBoxFlat:
    var box := surface(color, radius)
    box.set_border_width_all(1)
    box.border_color = Color(BORDER, border_alpha)
    return box

static func card_surface() -> StyleBoxFlat:
    return bordered_surface(PANEL, RADIUS_CARD)

static func drawer_surface() -> StyleBoxFlat:
    var box := bordered_surface(PANEL, RADIUS_CARD, .48)
    box.set_content_margin_all(3)
    return box

static func modal_surface() -> StyleBoxFlat:
    var box := bordered_surface(PANEL_RAISED, RADIUS_MODAL, .72)
    box.set_border_width_all(2)
    box.set_content_margin_all(5)
    box.shadow_size = 12
    box.shadow_color = Color.BLACK
    box.shadow_offset = Vector2(0, 6)
    return box

static func stage_surface() -> StyleBoxFlat:
    return bordered_surface(STAGE, RADIUS_CARD, .22)

static func role_accent(role: String) -> Color:
    match role:
        "primary", "choice", "play", "practice":
            return MINT
        "settings", "listen":
            return BLUE
        "review", "retry":
            return AMBER
        "danger":
            return CORAL
        "library":
            return STONE
        _:
            return SLATE

static func role_fill(role: String, selected: bool = false) -> Color:
    match role:
        "primary", "play":
            return Color("#286E60")
        "choice":
            return Color("#286E60") if selected else PANEL_RECESSED
        "settings", "listen":
            return Color("#253C4C")
        "review", "retry":
            return Color("#3A3029")
        "danger":
            return Color("#39292B")
        "library":
            return PANEL_RECESSED
        "secondary":
            return PANEL_RAISED
        _:
            return Color(PANEL_RECESSED, .25)

static func create() -> Theme:
    var theme := Theme.new()
    theme.default_font = font()
    theme.default_font_size = 16
    for control in ["Label", "Button", "LineEdit", "SpinBox", "CheckButton",
            "OptionButton", "PopupMenu", "TextEdit"]:
        theme.set_color("font_color", control, STONE)
        theme.set_color("font_hover_color", control, FOCUS)
        theme.set_color("font_focus_color", control, STONE)
        theme.set_color("font_pressed_color", control, STONE)
        theme.set_color("font_disabled_color", control, Color(SLATE, .52))
    theme.set_color("font_placeholder_color", "LineEdit", Color(SLATE, .73))
    theme.set_color("caret_color", "LineEdit", MINT)
    theme.set_color("selection_color", "LineEdit", Color(TEAL, .28))
    theme.set_color("font_selected_color", "LineEdit", FOCUS)
    theme.set_color("font_readonly_color", "LineEdit", SLATE)

    # Clear interaction affordances for fields without website-like neon
    # rings. Every form uses the same fill, spacing, focus and error states.
    var input := bordered_surface(PANEL_RECESSED, RADIUS_INPUT, .42)
    input.set_content_margin_all(12)
    var hovered := input.duplicate() as StyleBoxFlat
    hovered.bg_color = PANEL_RAISED
    hovered.border_color = Color(TEAL, .50)
    var focus := surface(Color.TRANSPARENT, RADIUS_INPUT)
    focus.set_border_width_all(2)
    focus.border_color = FOCUS
    var readonly := input.duplicate() as StyleBoxFlat
    readonly.bg_color = Color(FOREST, .8)
    readonly.border_color = Color(SAGE, .16)
    for control in ["LineEdit", "SpinBox", "OptionButton", "PopupMenu", "TextEdit"]:
        theme.set_stylebox("normal", control, input)
        theme.set_stylebox("panel", control, input)
        theme.set_stylebox("hover", control, hovered)
        theme.set_stylebox("pressed", control, hovered)
        theme.set_stylebox("focus", control, focus)
        theme.set_stylebox("read_only", control, readonly)
        theme.set_stylebox("disabled", control, readonly)
    var scrollbar := surface(Color(FOREST, .6), 4)
    scrollbar.set_content_margin_all(0)
    var grabber := surface(Color(SAGE, .65), 4)
    grabber.set_content_margin_all(0)
    theme.set_stylebox("scroll", "VScrollBar", scrollbar)
    theme.set_stylebox("grabber", "VScrollBar", grabber)
    theme.set_stylebox("grabber_highlight", "VScrollBar",
        surface(Color(TEAL, .7), 4))
    theme.set_stylebox("grabber_pressed", "VScrollBar", grabber)
    return theme

static func notation_material() -> ShaderMaterial:
    var shader := Shader.new()
    shader.code = """shader_type canvas_item;
render_mode unshaded;
void fragment() {
    vec4 sample_color = texture(TEXTURE, UV);
    float ink = 1.0 - dot(sample_color.rgb, vec3(0.2126, 0.7152, 0.0722));
    COLOR = vec4(vec3(0.149, 0.239, 0.204), sample_color.a * ink);
}
"""
    var material := ShaderMaterial.new()
    material.shader = shader
    return material
