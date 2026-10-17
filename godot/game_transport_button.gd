extends Button

# Physical transport key with independently laid-out icon and label.
# Input goes through Button.pressed; this script never advances the lesson.
const Design := preload("res://practice_theme.gd")
const TEAL := Design.MINT
const AMBER := Design.AMBER
const BLUE := Design.BLUE
const DIM := Color("#64847A")

var action_kind := "play"
var live := false
var pointer_inside := false
var down := false
var hover_phase := 0.0
var press_phase := 0.0
var release_flash := 0.0
var activity_time := 0.0

func _init() -> void:
    # Godot's default centred Button label would overlap our icon. Keep text
    # for accessibility and automation, but paint it in an independent region.
    for state in ["font_color", "font_hover_color", "font_pressed_color",
            "font_hover_pressed_color", "font_focus_color", "font_disabled_color"]:
        add_theme_color_override(state, Color.TRANSPARENT)
    focus_mode = Control.FOCUS_ALL

func _ready() -> void:
    mouse_entered.connect(func(): pointer_inside = true)
    mouse_exited.connect(func(): pointer_inside = false)
    button_down.connect(func(): down = true)
    button_up.connect(func():
        down = false
        release_flash = 1.0)
    pressed.connect(func(): release_flash = 1.0)
    focus_entered.connect(queue_redraw)
    focus_exited.connect(queue_redraw)
    resized.connect(func(): pivot_offset = size * .5)
    pivot_offset = size * .5

func configure(kind: String, playing: bool = false) -> void:
    if action_kind != kind or live != playing:
        action_kind = kind
        live = playing
        activity_time = 0.0
        queue_redraw()

func _process(delta: float) -> void:
    if not is_visible_in_tree():
        return
    var want_hover := 1.0 if (pointer_inside or has_focus()) and not disabled else 0.0
    var want_press := 1.0 if down and not disabled else 0.0
    var h := move_toward(hover_phase, want_hover, delta * 8.0)
    var p := move_toward(press_phase, want_press, delta * 14.0)
    var animating := absf(h - hover_phase) > .0001 or absf(p - press_phase) > .0001
    hover_phase = h
    press_phase = p
    if release_flash > 0:
        release_flash = maxf(0.0, release_flash - delta * 4.8)
        animating = true
    if live and not disabled:
        activity_time += delta
        animating = true
    if animating:
        # The button's layout slot and its keyboard focus remain unchanged.
        var scale_factor := 1.0 + .013 * hover_phase - .033 * press_phase + .008 * release_flash
        scale = Vector2.ONE * scale_factor
        queue_redraw()

func _draw() -> void:
    if size.x < 100 or size.y < 35:
        return
    var color := AMBER if action_kind == "retry" else BLUE if action_kind == "listen" else TEAL
    if disabled:
        color = DIM
    var glow := .13 * hover_phase + .11 * release_flash
    if live and not disabled:
        glow += .08 + .055 * (1.0 + sin(activity_time * 3.3))
    var mid := Vector2(35.0, size.y * .5)
    # Subtle inset above and raised lower lip. The StyleBox owns shadows,
    # border, hover, and depressed depth; this overlay contains no fake UI.
    draw_line(Vector2(15, 7), Vector2(size.x - 15, 7),
        Color("#FFFFFF", .06 + .075 * hover_phase), 1.0, true)
    draw_line(Vector2(15, size.y - 6), Vector2(size.x - 15, size.y - 6),
        Color(color, .16 + glow), 2.0, true)
    draw_circle(mid, 23.0, Color(color, .045 + glow * .13))
    draw_circle(mid, 17.0, Color(color, .065 + glow * .20))
    draw_line(Vector2(66, 16), Vector2(66, size.y - 16),
        Color(color, .17 + glow * .25), 1.0, true)
    match action_kind:
        "pause":
            draw_rect(Rect2(mid.x - 6, mid.y - 9, 4.2, 18), color)
            draw_rect(Rect2(mid.x + 2, mid.y - 9, 4.2, 18), color)
        "retry":
            draw_arc(mid, 9, -.5 * PI, 1.23 * PI, 40, color, 2.6, true)
            draw_colored_polygon(PackedVector2Array([
                mid + Vector2(-11, -9), mid + Vector2(-10, 1),
                mid + Vector2(-1, -6)]), color)
        "listen":
            draw_circle(mid + Vector2(-7, 0), 3.2, color)
            draw_arc(mid + Vector2(-6, 0), 7.3, -.37 * PI, .37 * PI, 28, color, 2.2, true)
            draw_arc(mid + Vector2(-6, 0), 12.0, -.37 * PI, .37 * PI, 28, color, 2.2, true)
        "practice":
            draw_line(mid + Vector2(-9, 0), mid + Vector2(9, 0), color, 2.5, true)
            draw_line(mid + Vector2(-9, 0), mid + Vector2(-1, -7), color, 2.5, true)
            draw_line(mid + Vector2(-9, 0), mid + Vector2(-1, 7), color, 2.5, true)
        _:
            draw_colored_polygon(PackedVector2Array([
                mid + Vector2(-5, -9), mid + Vector2(10, 0),
                mid + Vector2(-5, 9)]), color)
    var font: Font = get_theme_font("font")
    var font_size: int = get_theme_font_size("font_size")
    var available: float = maxf(32.0, size.x - 86.0)
    while font_size > 12 and font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT,
            -1, font_size).x > available:
        font_size -= 1
    var ink := Design.FOCUS if not disabled else Design.SAGE
    var label_width := font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x
    var label_x := 76.0 + maxf(0.0, (available - label_width) * .5)
    var baseline := (size.y + font.get_ascent(font_size) - font.get_descent(font_size)) * .5
    draw_string(font, Vector2(label_x, baseline), text,
        HORIZONTAL_ALIGNMENT_LEFT, available, font_size, ink)
