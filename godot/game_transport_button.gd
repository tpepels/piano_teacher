extends Button

# Physical transport key with independently laid-out icon and label.
# Input goes through Button.pressed; this script never advances the lesson.
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
var activity_time := 0.0
var live_redraw_elapsed := 0.0

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
        live_redraw_elapsed += maxf(0.0, delta)
        if live_redraw_elapsed >= .075:
            live_redraw_elapsed = fposmod(live_redraw_elapsed, .075)
            animating = true
    else:
        live_redraw_elapsed = 0.0
    if animating:
        # The button's layout slot and its keyboard focus remain unchanged.
        var scale_factor := 1.0 + .004 * hover_phase - .012 * press_phase
        scale = Vector2.ONE * scale_factor
        queue_redraw()

func _draw() -> void:
    if size.x < 100 or size.y < 35:
        return
    var color := TEAL if action_kind in ["play", "pause", "practice"] else Design.STONE
    if disabled:
        color = DIM
    var mid := Vector2(25.0, size.y * .5)
    # An unframed icon and label retain the physical control's hierarchy.
    # No medallion, glowing lip or decorative divider competes with the score.
    match action_kind:
        "pause":
            draw_rect(Rect2(mid.x - 5, mid.y - 7, 3.2, 14), color)
            draw_rect(Rect2(mid.x + 2, mid.y - 7, 3.2, 14), color)
        "retry":
            draw_arc(mid, 7, -.5 * PI, 1.23 * PI, 28, color, 1.8, true)
            draw_colored_polygon(PackedVector2Array([
                mid + Vector2(-8, -7), mid + Vector2(-8, 0),
                mid + Vector2(-1, -5)]), color)
        "listen":
            draw_circle(mid + Vector2(-5, 0), 2.2, color)
            draw_arc(mid + Vector2(-5, 0), 5.5, -.37 * PI, .37 * PI, 20, color, 1.6, true)
            draw_arc(mid + Vector2(-5, 0), 9.0, -.37 * PI, .37 * PI, 24, color, 1.6, true)
        "practice":
            draw_line(mid + Vector2(-7, 0), mid + Vector2(7, 0), color, 1.8, true)
            draw_line(mid + Vector2(-7, 0), mid + Vector2(-1, -5), color, 1.8, true)
            draw_line(mid + Vector2(-7, 0), mid + Vector2(-1, 5), color, 1.8, true)
        _:
            draw_colored_polygon(PackedVector2Array([
                mid + Vector2(-4, -7), mid + Vector2(8, 0),
                mid + Vector2(-4, 7)]), color)
    var font: Font = get_theme_font("font")
    var font_size: int = get_theme_font_size("font_size")
    var available: float = maxf(32.0, size.x - 60.0)
    while font_size > 12 and font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT,
            -1, font_size).x > available:
        font_size -= 1
    var ink := Design.FOCUS if not disabled else Design.SLATE
    var label_width := font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x
    var label_x := 46.0 + maxf(0.0, (available - label_width) * .5)
    var baseline := (size.y + font.get_ascent(font_size) - font.get_descent(font_size)) * .5
    draw_string(font, Vector2(label_x, baseline), text,
        HORIZONTAL_ALIGNMENT_LEFT, available, font_size, ink)
