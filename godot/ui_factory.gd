extends RefCounted
# Stateless shared construction. The owning screen connects user intent.
const Design := preload("res://practice_theme.gd")
const ActionButton := preload("res://action_button.gd")

static func font_size(base: int, scale: float = 1.0) -> int:
    return maxi(14, int(round(float(base) * scale)))

static func label(value: String, size: int, color: Color, bold := false,
        scale: float = 1.0) -> Label:
    var control := Label.new()
    control.text = value
    control.add_theme_color_override("font_color", color)
    control.set_meta("ui_font_base", size)
    control.add_theme_font_size_override("font_size", font_size(size, scale))
    control.add_theme_font_override("font", Design.font(700 if bold else 400))
    control.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    control.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    return control

static func title(value: String, size: int = 28, scale: float = 1.0) -> Label:
    var control := label(value, size, Design.STONE, false, scale)
    control.add_theme_font_override("font", Design.title_font())
    return control

static func stack(separation: int = 12) -> VBoxContainer:
    var control := VBoxContainer.new()
    control.add_theme_constant_override("separation", separation)
    return control

static func button(value: String, role: String = "secondary", scale: float = 1.0) -> Button:
    var control := ActionButton.new()
    control.text = value
    control.clip_text = false
    control.set_meta("ui_font_base", 15)
    control.add_theme_font_size_override("font_size", font_size(15, scale))
    control.configure(role)
    var width: float = Design.font(400).get_string_size(
        value, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size(15, scale)).x
    control.custom_minimum_size = Vector2(
        maxf(96.0, width + 48.0 * scale), 38.0 * scale)
    return control

static func card() -> PanelContainer:
    var panel := PanelContainer.new()
    panel.add_theme_stylebox_override("panel", Design.card_surface())
    return panel

static func card_body(panel: PanelContainer, margin: int = 28) -> MarginContainer:
    var body := MarginContainer.new()
    for side in ["left", "right", "top", "bottom"]:
        body.add_theme_constant_override("margin_" + side, margin)
    panel.add_child(body)
    return body
