extends Button

# Physical transport key. Button owns input; this canvas only presents it.
# Keep the real text available to accessibility and automation.
const Design := preload("res://practice_theme.gd")
const TEAL := Design.MINT
const DIM := Design.SLATE

var action_kind := "play"
var live := false
var pointer_inside := false
var down := false
var hover_phase := 0.0
var press_phase := 0.0
var release_flash := 0.0
var _was_disabled := false
var _keycap := StyleBoxFlat.new()

func _init() -> void:
    for state in ["font_color", "font_hover_color", "font_pressed_color",
            "font_hover_pressed_color", "font_focus_color", "font_disabled_color"]:
        add_theme_color_override(state, Color.TRANSPARENT)
    focus_mode = Control.FOCUS_ALL
    _keycap.set_corner_radius_all(4)
    _keycap.set_border_width_all(1)
    set_process(false)

func _ready() -> void:
    set_process(false)
    mouse_entered.connect(func():
        pointer_inside = true
        _wake_motion())
    mouse_exited.connect(func():
        pointer_inside = false
        _wake_motion())
    button_down.connect(func():
        if not disabled:
            down = true
            _wake_motion())
    button_up.connect(func():
        down = false
        _wake_motion())
    pressed.connect(func():
        if not disabled:
            release_flash = 1.0
            _wake_motion())
    focus_entered.connect(_wake_motion)
    focus_exited.connect(_wake_motion)
    visibility_changed.connect(func():
        if not is_visible_in_tree():
            pointer_inside = false
            _rest_motion()
        else:
            _wake_motion())

func configure(kind: String, playing: bool = false) -> void:
    if action_kind != kind or live != playing:
        action_kind = kind
        live = playing
        queue_redraw()

func _wake_motion() -> void:
    if disabled or not is_visible_in_tree():
        _rest_motion()
    else:
        set_process(true)
    queue_redraw()

func _rest_motion() -> void:
    down = false
    hover_phase = 0.0
    press_phase = 0.0
    release_flash = 0.0
    set_process(false)

func _process(delta: float) -> void:
    if disabled or not is_visible_in_tree():
        _rest_motion()
        queue_redraw()
        return
    var step: float = maxf(0.0, delta)
    var want_hover := 1.0 if pointer_inside or has_focus() else 0.0
    var want_press := 1.0 if down else 0.0
    hover_phase = move_toward(hover_phase, want_hover, step * 9.0)
    press_phase = move_toward(press_phase, want_press, step * 16.0)
    release_flash = maxf(0.0, release_flash - step * 5.5)
    queue_redraw()
    # A held hover, keyboard focus, held press and live playback are static.
    # Only transitions need frames; the layout slot and hit area never move.
    set_process(hover_phase != want_hover or press_phase != want_press
        or release_flash > 0.0)

func _shortcut_label() -> String:
    match action_kind:
        "retry":
            return "R"
        "play", "pause":
            return "Space"
        "listen", "practice":
            return "L"
        _:
            return ""

func _draw() -> void:
    # BaseButton redraws when disabled changes, even while processing sleeps.
    if disabled:
        _rest_motion()
    elif _was_disabled:
        pointer_inside = is_hovered()
        _wake_motion()
    _was_disabled = disabled
    if size.x < 100 or size.y < 35:
        return
    var primary: bool = action_kind in ["play", "pause"]
    var ink: Color = DIM if disabled else Design.NIGHT if primary else Design.FOCUS
    var font: Font = get_theme_font("font")
    var font_size: int = clampi(get_theme_font_size("font_size"), 12, 24)
    var key_size: int = 11 if size.x < 190.0 else clampi(font_size - 4, 11, 13)
    var key_label: String = _shortcut_label()
    var padding: float = 12.0 if size.x < 190.0 else 18.0
    var key_width: float = maxf(24.0, ceilf(font.get_string_size(key_label,
        HORIZONTAL_ALIGNMENT_LEFT, -1, key_size).x) + 12.0) if not key_label.is_empty() else 0.0
    var key_x: float = size.x - padding - key_width
    var group_space: float = key_x - padding - (10.0 if key_width > 0.0 else 0.0)
    var label_offset: float = 27.0 if size.x < 190.0 else 30.0
    var available: float = maxf(1.0, group_space - label_offset)
    while font_size > 12 and font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT,
            -1, font_size).x > available:
        font_size -= 1
    var label: String = text
    if font.get_string_size(label, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x > available:
        while not label.is_empty() and font.get_string_size(label + "…",
                HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x > available:
            label = label.left(label.length() - 1)
        label += "…"
    var label_width: float = font.get_string_size(label,
        HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x
    var group_x: float = padding + maxf(0.0, (group_space - label_offset - label_width) * .5)
    var lift: float = -hover_phase + 2.0 * press_phase - .8 * sin(release_flash * PI)
    var mid := Vector2(group_x + 10.0, size.y * .5 + lift)
    match action_kind:
        "pause":
            draw_rect(Rect2(mid.x - 5.5, mid.y - 7, 4.0, 14), ink)
            draw_rect(Rect2(mid.x + 1.5, mid.y - 7, 4.0, 14), ink)
        "retry":
            draw_arc(mid, 7, -.5 * PI, 1.23 * PI, 28, ink, 1.8, true)
            draw_colored_polygon(PackedVector2Array([
                mid + Vector2(-8, -7), mid + Vector2(-8, 0),
                mid + Vector2(-1, -5)]), ink)
        "listen":
            # Speaker silhouette stays distinct from Play's single triangle.
            draw_colored_polygon(PackedVector2Array([
                mid + Vector2(-8, -3), mid + Vector2(-4, -3),
                mid + Vector2(1, -7), mid + Vector2(1, 7),
                mid + Vector2(-4, 3), mid + Vector2(-8, 3)]), ink)
            draw_arc(mid + Vector2(-1, 0), 7, -.28 * PI, .28 * PI, 16, ink, 1.6, true)
            draw_arc(mid + Vector2(-1, 0), 11, -.25 * PI, .25 * PI, 20, ink, 1.6, true)
        "practice":
            draw_line(mid + Vector2(-7, 0), mid + Vector2(7, 0), ink, 1.8, true)
            draw_line(mid + Vector2(-7, 0), mid + Vector2(-1, -5), ink, 1.8, true)
            draw_line(mid + Vector2(-7, 0), mid + Vector2(-1, 5), ink, 1.8, true)
        _:
            draw_colored_polygon(PackedVector2Array([
                mid + Vector2(-4, -7), mid + Vector2(8, 0),
                mid + Vector2(-4, 7)]), ink)
    var baseline: float = (size.y + font.get_ascent(font_size)
        - font.get_descent(font_size)) * .5 + lift
    draw_string(font, Vector2(group_x + label_offset, baseline), label,
        HORIZONTAL_ALIGNMENT_LEFT, available, font_size, ink)
    if key_width <= 0.0:
        return
    var key_rect := Rect2(key_x, size.y * .5 - 12.0 + lift, key_width, 24.0)
    _keycap.bg_color = Color(ink, .06 if disabled else .10 if primary else .055)
    _keycap.border_color = Color(ink, .16 if disabled else .24 + hover_phase * .10)
    draw_style_box(_keycap, key_rect)
    # A shallow bottom lip compresses with the physical key press.
    draw_line(key_rect.position + Vector2(4, 21), key_rect.end - Vector2(4, 3),
        Color(ink, .18 * (1.0 - press_phase)), 1.0, true)
    var key_text_width: float = font.get_string_size(key_label,
        HORIZONTAL_ALIGNMENT_LEFT, -1, key_size).x
    var key_baseline: float = key_rect.get_center().y + (
        font.get_ascent(key_size) - font.get_descent(key_size)) * .5
    draw_string(font, Vector2(key_x + (key_width - key_text_width) * .5, key_baseline),
        key_label, HORIZONTAL_ALIGNMENT_LEFT, key_width, key_size, ink)
