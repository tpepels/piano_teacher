extends Control

const Design := preload("res://practice_theme.gd")

# One viewport-wide set of rules. Notes scroll through it; the same measured
# Y coordinates keep the rules aligned with every engraved system.
var staff_lines: Array = []
var active_hand := "both"
var viewport_left := 0.0
var viewport_width := 0.0

func _init() -> void:
    mouse_filter = Control.MOUSE_FILTER_IGNORE
    focus_mode = Control.FOCUS_NONE

func set_rails(lines: Array) -> void:
    staff_lines = lines.duplicate()
    queue_redraw()

func set_hand(hand: String) -> void:
    if active_hand != hand:
        active_hand = hand
        queue_redraw()

func set_viewport_span(left: float, width: float) -> void:
    if viewport_left != left or viewport_width != width:
        viewport_left = left
        viewport_width = width
        queue_redraw()

static func draw_rules(canvas: Control, lines: Array, left: float, right: float,
        hand: String) -> void:
    if lines.size() < 2 or right <= left:
        return
    var transform := canvas.get_global_transform_with_canvas()
    var scale_y: float = maxf(.001, transform.y.length())
    var gap: float = absf(float(lines[1]) - float(lines[0])) * scale_y
    var weight: float = 2.0 if gap >= 12.0 else 1.0
    for index in range(lines.size()):
        var active: bool = lines.size() != 10 or hand not in ["right", "left"] \
            or (index < 5) == (hand == "right")
        var ink: Color = Design.STAFF_INK if active else Design.STAFF_MUTED
        # Whole pixel rules do not shimmer or fade at fractional staff Y.
        var screen_y: float = (transform * Vector2(0.0, float(lines[index]))).y
        var top: float = (roundf(screen_y - weight * .5) - transform.origin.y) / scale_y
        canvas.draw_rect(Rect2(left, top, right-left, weight/scale_y), ink)

func _draw() -> void:
    if staff_lines.is_empty() or size.x <= 1.0 or size.y <= 1.0:
        return
    var lines: Array = []
    for normalized in staff_lines:
        lines.append(float(normalized) * size.y)
    draw_rules(self, lines, viewport_left, viewport_left + viewport_width, active_hand)
