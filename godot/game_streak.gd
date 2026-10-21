extends Control

const Design := preload("res://practice_theme.gd")

# Three clean passes rendered as luminous instrument indicators.
# Engine-assessed result/streak are passed in; this component never scores.
const ON := Design.MINT
const OFF := Design.SAGE
const BAD := Design.CORAL

var value := 0
var required := 3
var state := "idle"
var reveal := 0.0
var unlock_wave := -1.0

func pulse_unlock() -> void:
    # Only the backend's actual left/right/both hand unlock starts this wave.
    unlock_wave = 0.0
    _wake_animation()

func _init() -> void:
    mouse_filter = Control.MOUSE_FILTER_IGNORE
    focus_mode = Control.FOCUS_NONE
    custom_minimum_size = Vector2(155, 32)
    size_flags_horizontal = Control.SIZE_SHRINK_END
    set_process(false)

func _ready() -> void:
    set_process(reveal > 0.0 or unlock_wave >= 0.0)

func _notification(what: int) -> void:
    if what == NOTIFICATION_VISIBILITY_CHANGED and not is_visible_in_tree():
        reveal = 0.0
        unlock_wave = -1.0
        set_process(false)

func present(info: Dictionary) -> void:
    var next_total := maxi(1, int(info.get("required", 3)))
    var next_value := clampi(int(info.get("streak", 0)), 0, next_total)
    var next_state := str(info.get("kind", "idle"))
    if next_value != value or next_state != state or required != next_total:
        required = next_total
        value = next_value
        state = next_state
        reveal = 1.0 if state == "success" and value > 0 else 0.0
        if state in ["idle", "preview", "learn"]:
            unlock_wave = -1.0
        _wake_animation()

func _wake_animation() -> void:
    if not is_visible_in_tree():
        reveal = 0.0
        unlock_wave = -1.0
    set_process(reveal > 0.0 or unlock_wave >= 0.0)
    queue_redraw()

func _process(delta: float) -> void:
    var step: float = maxf(0.0, delta)
    if reveal > 0.0:
        reveal = maxf(0.0, reveal - step * 2.4)
        queue_redraw()
    if unlock_wave >= 0.0:
        unlock_wave += step * 1.8
        if unlock_wave >= 1.0:
            unlock_wave = -1.0
        queue_redraw()
    set_process(reveal > 0.0 or unlock_wave >= 0.0)

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
    var span: float = minf(45.0, (w - 36.0) / maxf(1.0,float(required)))
    var first: float = (w - span * float(required-1)) * .5
    var segment_width: float = maxf(4.0, minf(33.0, span - 9.0))
    var filled_tone: Color = BAD if state == "retry" else ON
    var dim_tone := Color("#36544B")

    draw_line(Vector2(first, mid), Vector2(first + span * float(required-1), mid),
        Color(OFF, .43), 2.0, true)
    if unlock_wave >= 0.0:
        var wave_x: float = lerpf(first - 14.0, first + span * float(required-1) + 14.0, unlock_wave)
        draw_line(Vector2(first, mid), Vector2(wave_x, mid),
            Color(ON, .68), 3.2, true)
        draw_circle(Vector2(wave_x, mid), 7.0, Color(ON, .08))
        draw_circle(Vector2(wave_x, mid), 3.1, Color(ON, .92))
    for i in range(required):
        var p := Vector2(first + span * float(i), mid)
        var filled: bool = i < value and state != "preview"
        var flash: float = reveal if filled and i == value - 1 and state == "success" else 0.0
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
        else:
            # An unlit core remains clearly visible on dark backgrounds.
            draw_circle(p, 1.7, Color(OFF, .65))
