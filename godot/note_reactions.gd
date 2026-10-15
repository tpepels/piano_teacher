extends Control

const Ink := preload("res://notehead_ink.gd")
const HIT := Color("#88EBC3")
const TIMING := Color("#E6B877")
var hit_pulses: Array = []
var active_page := 0
var crop_origin := Vector2.ZERO
var crop_size := Vector2.ONE
var staff_gap_fraction := 0.02

func _init() -> void:
    mouse_filter = Control.MOUSE_FILTER_IGNORE
    focus_mode = Control.FOCUS_NONE

func _draw() -> void:
    if hit_pulses.is_empty():
        return
    var now_ms: int = Time.get_ticks_msec()
    var gap: float = maxf(5.0, staff_gap_fraction * size.y)
    var base: Vector2 = Ink.radii(gap)
    for hit in hit_pulses:
        if int(hit.get("page", -1)) != active_page:
            continue
        var life_ms: int = int(hit.get("duration_ms", 260))
        var remaining: float = clampf(float(int(hit.get("until_ms", 0)) - now_ms)
            / float(maxi(1, life_ms)), 0.0, 1.0)
        if remaining <= 0.0:
            continue
        var progress: float = 1.0 - remaining
        var position := size * ((Vector2(float(hit.get("x", 0.0)),
            float(hit.get("y", 0.0))) - crop_origin) / crop_size)
        var radius: Vector2 = base * (1.12 + 0.55 * progress)
        var tone: Color = HIT if str(hit.get("status", "")) == "on_time" else TIMING
        draw_circle(position, gap * 0.9, Color(tone, remaining * 0.055))
        draw_polyline(Ink.ellipse(position, radius.x, radius.y),
            Color(tone, remaining * .53), 1.4, true)
