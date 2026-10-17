extends Control

const Design := preload("res://practice_theme.gd")

# Three clean passes rendered as luminous instrument indicators.
# Engine-assessed result/streak are passed in; this component never scores.
const ON := Design.MINT
const OFF := Design.SAGE
const BAD := Design.CORAL

var value := 0
var state := "idle"
var reveal := 0.0
var unlock_wave := -1.0

func pulse_unlock() -> void:
    # Only the backend's actual left/right/both hand unlock starts this wave.
    unlock_wave = 0.0
    queue_redraw()

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
    if unlock_wave >= 0.0:
        unlock_wave += delta * 1.05
        if unlock_wave >= 1.0:
            unlock_wave = -1.0
        queue_redraw()

func _pill(center: Vector2, width: float, height: float, tone: Color) -> void:
    var radius: float = height * .5
    draw_rect(Rect2(center.x - width * .5 + radius, center.y - radius,
        maxf(0.0, width - 2.0 * radius), height), tone)
    draw_circle(center + Vector2(-width * .5 + radius, 0), radius, tone)
    draw_circle(center + Vector2(width * .5 - radius, 0), radius, tone)

func _draw() -> void:
    # Three luminous musical milestones, not a small checkbox widget.
    # The real backend streak remains the only source of filled segments.
    var w: float = size.x
    if w < 58.0 or size.y < 20.0:
        return
    var mid: float = size.y * .5
    var span: float = minf(45.0, (w - 36.0) / 3.0)
    var first: float = (w - span * 2.0) * .5
    var segment_width: float = minf(33.0, span - 9.0)
    var filled_tone: Color = BAD if state == "retry" else ON
    var dim_tone := Color("#36544B")

    draw_line(Vector2(first, mid), Vector2(first + span * 2.0, mid),
        Color(OFF, .43), 2.0, true)
    if unlock_wave >= 0.0:
        var wave_x: float = lerpf(first - 14.0, first + span * 2.0 + 14.0, unlock_wave)
        draw_line(Vector2(first, mid), Vector2(wave_x, mid),
            Color(ON, .68), 3.2, true)
        draw_circle(Vector2(wave_x, mid), 12.0, Color(ON, .11))
        draw_circle(Vector2(wave_x, mid), 3.1, Color(ON, .92))
    for i in range(3):
        var p := Vector2(first + span * float(i), mid)
        var filled: bool = i < value and state != "preview"
        var flash: float = reveal if filled and state == "success" else 0.0
        if filled:
            _pill(p, segment_width + 13.0 + flash * 5.0,
                23.0 + flash * 5.0, Color(filled_tone, .045 + flash * .15))
            _pill(p, segment_width + 5.0, 17.0,
                Color(filled_tone, .09 + flash * .15))
        _pill(p, segment_width, 12.0, Color("#0D2521"))
        _pill(p, segment_width - 3.0, 9.0,
            Color(filled_tone, .90) if filled else dim_tone)
        if filled:
            draw_line(p + Vector2(-segment_width * .3, -1.8),
                p + Vector2(segment_width * .3, -1.8),
                Color("#E6FFF3", .44 + flash * .45), 1.2, true)
            if flash > .025:
                for ray in range(6):
                    var angle: float = TAU * float(ray) / 6.0
                    var outward := Vector2(cos(angle), sin(angle))
                    var start: Vector2 = p + outward * (13.0 + flash * 2.0)
                    draw_line(start, start + outward * flash * 9.0,
                        Color(filled_tone, flash * .64), 1.35, true)
        else:
            # An unlit core remains clearly visible on dark backgrounds.
            draw_circle(p, 1.7, Color(OFF, .65))
