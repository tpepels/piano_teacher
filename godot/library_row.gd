extends "res://action_button.gd"

const Palette := preload("res://practice_theme.gd")

# One focusable music tile, using real catalog text and a neutral piano mark.
# Both labels belong to the same button; the mark never implies album art.
var title_label: Label
var detail_label: Label
var text_scale := 1.0
var mark_face: StyleBoxFlat

func _init() -> void:
    super._init()
    custom_minimum_size = Vector2(0, 96)
    mark_face = Palette.bordered_surface(Color(Palette.PINE,.45), 8, .25)
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
    content.add_theme_constant_override("margin_left", 86)
    content.add_theme_constant_override("margin_right", 16)
    content.add_theme_constant_override("margin_top", 18)
    content.add_theme_constant_override("margin_bottom", 18)
    add_child(content)
    var lines := VBoxContainer.new()
    lines.mouse_filter = Control.MOUSE_FILTER_IGNORE
    lines.alignment = BoxContainer.ALIGNMENT_CENTER
    lines.add_theme_constant_override("separation", 8)
    content.add_child(lines)
    title_label = Label.new()
    title_label.name = "MusicTitle"
    title_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
    title_label.clip_text = true
    title_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
    title_label.add_theme_font_override("font", Palette.title_font())
    title_label.add_theme_font_size_override("font_size", roundi(20.0 * text_scale))
    title_label.add_theme_color_override("font_color", Palette.STONE)
    lines.add_child(title_label)
    detail_label = Label.new()
    detail_label.name = "MusicDetail"
    detail_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
    detail_label.clip_text = true
    detail_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
    detail_label.add_theme_font_size_override("font_size", roundi(14.0 * text_scale))
    detail_label.add_theme_color_override("font_color", Palette.SLATE)
    lines.add_child(detail_label)
    set_text_scale(text_scale)
    if has_meta("library_title"):
        _update_labels()

# Library entries are created after the main responsive-font pass. Apply
# the same display scale explicitly, without shrinking to the Button theme.
func set_text_scale(scale_factor: float) -> void:
    text_scale = clampf(scale_factor, 1.0, 1.75)
    if title_label == null or detail_label == null:
        return
    title_label.add_theme_font_size_override("font_size", roundi(20.0 * text_scale))
    detail_label.add_theme_font_size_override("font_size", roundi(14.0 * text_scale))
    # Keep the compact tile height until actual enlarged font metrics need
    # more room; viewport scaling alone must not create oversized cards.
    custom_minimum_size.y = maxf(96.0,
        title_label.get_line_height() + detail_label.get_line_height() + 44.0)
    queue_redraw()

func set_entry(title: String, detail: String, status: String = "") -> void:
    configure("library")
    # A music shelf: one ruled row, large title, and a single hover surface.
    # Do not fill the library with identical pretend album-art cards.
    var normal := Palette.surface(Color.TRANSPARENT, 5)
    normal.set_border_width(SIDE_BOTTOM, 1)
    normal.border_color = Color(Palette.SAGE,.30)
    add_theme_stylebox_override("normal", normal)
    var hover := normal.duplicate() as StyleBoxFlat
    hover.bg_color = Color(Palette.PINE,.48)
    hover.border_color = Color(Palette.MINT,.55)
    add_theme_stylebox_override("hover", hover)
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
    _update_labels()

func _update_labels() -> void:
    title_label.text = str(get_meta("library_title", ""))
    detail_label.text = str(get_meta("library_detail", ""))
    var status: String = str(get_meta("library_status", ""))
    if status == "error":
        title_label.add_theme_color_override("font_color", Palette.CORAL)
    elif status == "warning":
        title_label.add_theme_color_override("font_color", Palette.AMBER)
    else:
        title_label.add_theme_color_override("font_color", Palette.STONE)

func _draw() -> void:
    # Replace ActionButton's small left icon with a quiet, shared instrument
    # mark. No superclass _draw call: the two glyphs must not overlap.
    if size.x < 90.0 or size.y < 60.0:
        return
    var top: float = (size.y - 54.0) * .5
    var frame := Rect2(18.0, top, 50.0, 54.0)
    draw_style_box(mark_face, frame)
    var keyboard := Rect2(27.0, top + 13.0, 32.0, 29.0)
    draw_rect(keyboard, Color(Palette.STONE, .78))
    var key_width: float = keyboard.size.x / 4.0
    for key in range(1, 4):
        var x: float = keyboard.position.x + key_width * key
        draw_line(Vector2(x, keyboard.position.y),
            Vector2(x, keyboard.end.y), Color(Palette.PANEL_RECESSED, .8), 1.0)
        if key != 3:
            draw_rect(Rect2(x - 2.5, keyboard.position.y, 5.0, 17.0), Palette.PANEL_RECESSED)
    var arrow := Vector2(size.x-26,size.y*.5)
    draw_line(arrow-Vector2(6,0),arrow+Vector2(5,0),Palette.MINT,1.6,true)
    draw_line(arrow+Vector2(1,-4),arrow+Vector2(5,0),Palette.MINT,1.6,true)
    draw_line(arrow+Vector2(1,4),arrow+Vector2(5,0),Palette.MINT,1.6,true)
