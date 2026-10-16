extends Control

# Phase 7.7b: a bounded, deterministic impact effect on real MIDI feedback.
# No particles are spawned as nodes, and nothing here judges musical timing.
# Every attack is rendered in the same coordinates as the engraved notehead.
const Ink := preload("res://notehead_ink.gd")
const HIT := Color("#8DFFD3")
const TIMING := Color("#F0C785")
const ERROR := Color("#FF7779")
const MAX_VISIBLE_HITS := 16

var hit_pulses: Array = []
var wrong_ghosts: Array = []
var active_page := 0
var crop_origin := Vector2.ZERO
var crop_size := Vector2.ONE
var staff_gap_fraction := 0.02

func _init() -> void:
    mouse_filter = Control.MOUSE_FILTER_IGNORE
    focus_mode = Control.FOCUS_NONE

func _sheet_position(item: Dictionary) -> Vector2:
    return size * ((Vector2(float(item.get("x", 0.0)),
        float(item.get("y", 0.0))) - crop_origin) / crop_size)

func _remaining(item: Dictionary, now_ms: int, fallback_ms: int) -> float:
    var duration: int = maxi(1, int(item.get("duration_ms", fallback_ms)))
    return clampf(float(int(item.get("until_ms", 0)) - now_ms) /
        float(duration), 0.0, 1.0)

func _impact(center: Vector2, progress: float, gap: float,
        radii: Vector2, tone: Color, graded: bool) -> void:
    # The halo is behind the ink layer. It cannot paint over a notehead.
    var fade: float = pow(1.0 - progress, 1.35)
    var bloom: float = 1.0 - clampf(progress * 2.5, 0.0, 1.0)
    draw_circle(center, gap * (2.15 + progress), Color(tone, .055 * fade))
    draw_circle(center, gap * (1.36 + progress * .8),
        Color(tone, .11 * fade + .10 * bloom))
    draw_circle(center, gap * .82, Color(tone, .26 * bloom))
    draw_polyline(Ink.ellipse(center,
            radii.x * (1.38 + progress * 1.1),
            radii.y * (1.38 + progress * 1.1)),
        Color(tone, .82 * fade), 2.0, true)
    # Stable phase offsets prevent particle jitter when frames are skipped.
    # Chords share their light, but each note keeps its own bounded 12 sparks.
    var count: int = 12 if graded else 6
    for i in range(count):
        var angle: float = TAU * (float(i) + .17 * sin(center.x * .037 +
            float(i) * 5.13)) / float(count)
        var ray := Vector2(cos(angle), sin(angle))
        var stagger: float = .83 + .26 * sin(float(i) * 8.71 + center.y * .013)
        var travel: float = gap * (0.65 + 2.8 * progress) * stagger
        var point: Vector2 = center + ray * travel
        var radius: float = maxf(1.5, gap * (.092 + .035 * float(i % 3))) * fade
        if radius <= 0.2:
            continue
        draw_line(center + ray * (gap * .95), point,
            Color(tone, .22 * fade), maxf(.65, radius * .48), true)
        draw_circle(point, radius + gap * .06, Color(tone, .085 * fade))
        draw_circle(point, radius, Color(tone, .9 * fade))

func _draw() -> void:
    if hit_pulses.is_empty() and wrong_ghosts.is_empty():
        return
    var now_ms: int = Time.get_ticks_msec()
    var gap: float = maxf(5.0, staff_gap_fraction * size.y)
    var radii: Vector2 = Ink.radii(gap)
    for i in range(maxi(0, hit_pulses.size() - MAX_VISIBLE_HITS), hit_pulses.size()):
        var hit: Dictionary = hit_pulses[i]
        if int(hit.get("page", -1)) != active_page:
            continue
        var remaining: float = _remaining(hit, now_ms, 450)
        if remaining <= 0.0:
            continue
        var progress: float = 1.0 - remaining
        var tone: Color = HIT if str(hit.get("status", "")) == "on_time" else TIMING
        _impact(_sheet_position(hit), progress, gap, radii, tone, true)
    # Unexpected physical attacks never create success particles. Their
    # smaller coral sparks accompany the error outline on the top layer.
    for i in range(maxi(0, wrong_ghosts.size() - MAX_VISIBLE_HITS), wrong_ghosts.size()):
        var wrong: Dictionary = wrong_ghosts[i]
        if int(wrong.get("page", -1)) != active_page:
            continue
        var remaining: float = _remaining(wrong, now_ms, 420)
        if remaining <= 0.0:
            continue
        _impact(_sheet_position(wrong), 1.0 - remaining, gap,
            radii, ERROR, false)
