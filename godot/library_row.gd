extends "res://action_button.gd"

const Palette := preload("res://practice_theme.gd")

# One fully-clickable, focusable music row. Both lines belong to the same
# button, rather than squeezing title, format, location and BPM onto one line.
# Static labels add no per-frame animations or GPU effects.
var title_label: Label
var detail_label: Label

func _init() -> void:
    super._init()
    custom_minimum_size = Vector2(0, 76)
    size_flags_horizontal = Control.SIZE_EXPAND_FILL
    clip_text = false

func _ready() -> void:
    super._ready()
    if title_label != null:
        return
    var content := MarginContainer.new()
    content.name = "MusicRowContent"
    content.mouse_filter = Control.MOUSE_FILTER_IGNORE
    content.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    content.add_theme_constant_override("margin_left", 54)
    content.add_theme_constant_override("margin_right", 16)
    content.add_theme_constant_override("margin_top", 11)
    content.add_theme_constant_override("margin_bottom", 9)
    add_child(content)
    var lines := VBoxContainer.new()
    lines.mouse_filter = Control.MOUSE_FILTER_IGNORE
    lines.add_theme_constant_override("separation", 3)
    content.add_child(lines)
    title_label = Label.new()
    title_label.name = "MusicTitle"
    title_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
    title_label.clip_text = true
    title_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
    title_label.add_theme_font_size_override("font_size", 17)
    title_label.add_theme_color_override("font_color", Palette.STONE)
    lines.add_child(title_label)
    detail_label = Label.new()
    detail_label.name = "MusicDetail"
    detail_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
    detail_label.clip_text = true
    detail_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
    detail_label.add_theme_font_size_override("font_size", 13)
    detail_label.add_theme_color_override("font_color", Palette.SLATE)
    lines.add_child(detail_label)

func set_entry(title: String, detail: String, status: String = "") -> void:
    configure("library")
    # The real entry title remains machine-readable for keyboard navigation
    # and diagnostics while custom visible labels use clearer hierarchy.
    set_meta("library_title", title)
    set_meta("library_detail", detail)
    set_meta("library_status", status)
    # Keep the native Button's accessible label/keyboard identity. The
    # title is painted by a dedicated clipped Label for better typography,
    # so its duplicate native rendering is transparent, not removed.
    text = title
    clip_text = true
    for state_color in ["font_color", "font_hover_color", "font_pressed_color",
            "font_hover_pressed_color", "font_focus_color", "font_disabled_color"]:
        add_theme_color_override(state_color, Color.TRANSPARENT)
    tooltip_text = title + "\n" + detail
    if title_label == null:
        return
    title_label.text = title
    detail_label.text = detail
    if status == "error":
        title_label.add_theme_color_override("font_color", Palette.CORAL)
    elif status == "warning":
        title_label.add_theme_color_override("font_color", Palette.AMBER)
    else:
        title_label.add_theme_color_override("font_color", Palette.STONE)
