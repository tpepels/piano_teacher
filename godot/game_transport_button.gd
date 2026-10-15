extends Button

# Tactile piano-console transport control. Backend state alone decides whether
# the lesson is playing, paused or mastered.
const TEAL := Color("#91F4CC")
const AMBER := Color("#FFC68A")
const DIM := Color("#4B7168")

var action_kind := "play"
var live := false
var highlighted := false
var depressed := false
var hover_amount := 0.0
var press_amount := 0.0
var activity_time := 0.0

func _ready() -> void:
    mouse_entered.connect(func(): highlighted = true)
    mouse_exited.connect(func(): highlighted = false)
    button_down.connect(func(): depressed = true)
    button_up.connect(func(): depressed = false)
    focus_entered.connect(func(): highlighted = true)
    focus_exited.connect(func(): highlighted = false)
    resized.connect(func(): pivot_offset = size * 0.5)
    pivot_offset = size * 0.5

func configure(kind: String, playing: bool = false) -> void:
    if action_kind != kind or live != playing:
        action_kind = kind
        live = playing
        activity_time = 0.0
        queue_redraw()

func _process(delta: float) -> void:
    if not is_visible_in_tree():
        return
    var hover_target := 1.0 if highlighted and not disabled else 0.0
    var press_target := 1.0 if depressed and not disabled else 0.0
    var next_hover := move_toward(hover_amount, hover_target, delta * 8.0)
    var next_press := move_toward(press_amount, press_target, delta * 15.0)
    var changing := absf(next_hover - hover_amount) > 0.0001 or absf(next_press - press_amount) > 0.0001
    hover_amount = next_hover
    press_amount = next_press
    if live and not disabled:
        activity_time += delta
    if changing or (live and not disabled):
        var factor := 1.0 + hover_amount * 0.028 - press_amount * 0.055
        scale = Vector2(factor, factor)
        queue_redraw()

func _draw() -> void:
    if size.x < 12.0 or size.y < 12.0:
        return
    var accent := AMBER if action_kind == "retry" else TEAL
    var light := hover_amount * 0.26 + press_amount * 0.17
    if live and not disabled:
        light += 0.13 + 0.09 * (0.5 + 0.5 * sin(activity_time * 4.5))
    if disabled:
        light *= 0.2
        accent = DIM
    # Accent well, recessed icon, and contact-light along the lower lip.
    draw_rect(Rect2(7, 8, 3, size.y - 16), Color(accent, 0.36 + light))
    draw_line(Vector2(16, size.y - 5), Vector2(size.x - 16, size.y - 5),
        Color(accent, 0.2 + light), 2.0)
    var center := Vector2(29, size.y * 0.5)
    draw_circle(center, 16.0 + hover_amount * 1.5, Color(accent, 0.06 + light * 0.27))
    draw_arc(center, 13, -PI * 0.7, PI * 0.7, 30, Color(accent, 0.35 + light), 1.7, true)
    match action_kind:
        "pause":
            draw_rect(Rect2(center.x - 6, center.y - 7, 4, 14), accent)
            draw_rect(Rect2(center.x + 2, center.y - 7, 4, 14), accent)
        "retry":
            draw_arc(center, 7.5, -2.6, 2.4, 28, accent, 2.5, true)
            draw_colored_polygon(PackedVector2Array([
                center + Vector2(-10, -4), center + Vector2(-9, 4),
                center + Vector2(-2, -2)]), accent)
        "listen":
            draw_circle(center + Vector2(-6, 0), 3, accent)
            draw_arc(center + Vector2(-4, 0), 6.0, -PI * .4, PI * .4, 20, accent, 2, true)
            draw_arc(center + Vector2(-4, 0), 10.5, -PI * .4, PI * .4, 20, accent, 2, true)
        "practice":
            draw_line(center + Vector2(-7, 0), center + Vector2(7, 0), accent, 2.5, true)
            draw_line(center + Vector2(-7, 0), center + Vector2(-1, -6), accent, 2.5, true)
            draw_line(center + Vector2(-7, 0), center + Vector2(-1, 6), accent, 2.5, true)
        _:
            draw_colored_polygon(PackedVector2Array([
                center + Vector2(-4, -7), center + Vector2(8, 0),
                center + Vector2(-4, 7)]), accent)
