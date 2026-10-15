extends Control

# Three clean passes rendered as luminous instrument indicators.
# Engine-assessed result/streak are passed in; this component never scores.
const ON := Color("#7CF0C4")
const OFF := Color("#516D67")
const BAD := Color("#EF7776")

var value := 0
var state := "idle"
var reveal := 0.0

func _init() -> void:
    mouse_filter = Control.MOUSE_FILTER_IGNORE
    focus_mode = Control.FOCUS_NONE
    custom_minimum_size = Vector2(155, 32)
    size_flags_horizontal = Control.SIZE_SHRINK_END

func present(info: Dictionary) -> void:
    var next_value := clampi(int(info.get("streak", 0)), 0, 3)
    var next_state := str(info.get("kind", "idle"))
    if next_value != value or next_state != state:
        value = next_value
        state = next_state
        reveal = 1.0 if state in ["success", "retry"] else .0
        queue_redraw()

func _process(delta: float) -> void:
    if reveal > 0.001:
        reveal = maxf(0.0, reveal - delta * 1.1)
        queue_redraw()

func _draw() -> void:
    var w := size.x
    var mid := size.y * .5
    var spacing := minf(45.0, (w - 28) / 3.0)
    var start := (w - spacing * 2.0) * .5
    var tone := BAD if state == "retry" else ON
    draw_line(Vector2(start, mid), Vector2(start + spacing*2, mid),
        Color(OFF, .55), 3, true)
    for i in range(3):
        var pos := Vector2(start + spacing * i, mid)
        var filled := i < value and state != "preview"
        var glow := filled and state == "success"
        if glow:
            draw_circle(pos, 13 + reveal * 3, Color(ON, .09 + reveal * .16))
        draw_circle(pos, 9, Color("#182526"))
        draw_arc(pos, 9, 0, TAU, 28, Color(tone if filled else OFF, .9 if filled else .6), 2, true)
        if filled:
            draw_circle(pos, 4.6, tone)
        elif state == "retry":
            draw_circle(pos, 2.3, Color(BAD, .52))
        else:
            draw_circle(pos, 2.2, Color(OFF, .85))
