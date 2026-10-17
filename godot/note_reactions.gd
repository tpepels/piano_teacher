extends Control

# 7.7b - Resonance. Large, time-bounded MIDI-only note impacts. The effect
# is painted behind Verovio's own notation so a particle cannot erase pitch,
# fingering, note duration, or an accidental. No child nodes or random timers.
const Ink := preload("res://notehead_ink.gd")
const HIT := Color("#82F5C8")
const TIMING := Color("#F2C980")
const ERROR := Color("#FF9F98")
const PREVIEW := Color("#9ECAFF")
const MAX_VISIBLE_HITS := 16
const PARTICLE_COUNT := 16
const HIT_DURATION_MS := 450
const ERROR_DURATION_MS := 420

var hit_pulses: Array = []
var preview_pulses: Array = []
var wrong_ghosts: Array = []
var active_page := 0
var crop_origin := Vector2.ZERO
var crop_size := Vector2.ONE
var staff_gap_fraction := 0.02
var staff_lines: Array = []

func _init() -> void:
    mouse_filter = Control.MOUSE_FILTER_IGNORE
    focus_mode = Control.FOCUS_NONE
    # Light accumulates naturally when three notes of a chord are struck;
    # unlike opaque sprites, the actual white engraved ink stays untouched.
    var bloom_material := CanvasItemMaterial.new()
    # The moodboard's ivory score needs pigment rather than additive light:
    # ADD makes mint-white particles disappear on a pale background.
    bloom_material.blend_mode = CanvasItemMaterial.BLEND_MODE_MIX
    material = bloom_material

func _sheet_position(item: Dictionary) -> Vector2:
    return size * ((Vector2(float(item.get("x", 0.0)),
        float(item.get("y", 0.0))) - crop_origin) / crop_size)

func _remaining(item: Dictionary, now_ms: int, fallback_ms: int) -> float:
    var duration: int = maxi(1, int(item.get("duration_ms", fallback_ms)))
    return clampf(float(int(item.get("until_ms", 0)) - now_ms) /
        float(duration), 0.0, 1.0)

# Deterministic, note-specific particle positions. Frames can be skipped or
# redrawn at any frequency without a burst suddenly changing directions.
static func particle_endpoint(center: Vector2, gap: float,
        progress: float, index: int, count: int = PARTICLE_COUNT) -> Vector2:
    var p: float = clampf(progress, 0.0, 1.0)
    var wobble: float = .19 * sin(center.x * .013 + center.y * .021
        + float(index) * 4.37)
    var angle: float = TAU * (float(index) + wobble) / float(maxi(1, count))
    var stagger: float = .89 + .17 * sin(float(index) * 5.17 + center.y * .02)
    var distance: float = maxf(4.0, gap) * (1.05 + 3.4
        * (1.0 - pow(1.0 - p, 1.45))) * stagger
    return center + Vector2(cos(angle), sin(angle)) * distance

static func impact_reach(gap: float, progress: float) -> float:
    # Wider than the old ~1.4-notehead green ring, but independent of screen
    # resolution and still bounded on dense chords and smaller windows.
    return maxf(4.0, gap) * (1.65 + 3.35 * clampf(progress, 0.0, 1.0))

func _success_impact(center: Vector2, progress: float, gap: float,
        radii: Vector2, tone: Color) -> void:
    var fade: float = pow(1.0 - progress, 1.08)
    var attack: float = pow(1.0 - clampf(progress * 4.4, 0.0, 1.0), 1.2)
    var reach: float = impact_reach(gap, progress)
    # A broad soft halo, bright central attack and two expanding rings.
    # This must read as an actual piano strike from across the room.
    draw_circle(center, gap * (3.75 + progress * 1.3),
        Color(tone, .12 * fade))
    draw_circle(center, gap * (2.45 + progress * 1.2),
        Color(tone, .15 * fade + .10 * attack))
    draw_circle(center, gap * 1.48,
        Color(tone, .22 * fade + .40 * attack))
    draw_circle(center, gap * .68, Color.WHITE * Color(1, 1, 1,
        .36 * attack))
    draw_polyline(Ink.ellipse(center, reach, reach * .66),
        Color(tone, .34 * fade), 3.5, true)
    draw_polyline(Ink.ellipse(center, radii.x * (1.65 + progress * 2.0),
        radii.y * (1.65 + progress * 2.0)),
        Color(tone, .81 * fade), 2.7, true)

    # Sixteen sparks, initially luminous and moving away from the real
    # notehead. No separate particle emitters or per-frame allocations.
    for index in range(PARTICLE_COUNT):
        var endpoint: Vector2 = particle_endpoint(
            center, gap, progress, index)
        var ray: Vector2 = (endpoint - center).normalized()
        var radius: float = maxf(1.3, gap * (.10 + .036 * float(index % 3))) * fade
        if radius <= .16:
            continue
        draw_line(endpoint - ray * (gap * (.56 + .46 * progress)), endpoint,
            Color(tone, .64 * fade), maxf(1.0, radius * .72), true)
        draw_circle(endpoint, radius + gap * .12,
            Color(tone, .22 * fade))
        draw_circle(endpoint, radius, Color(tone, fade))

func _error_impact(center: Vector2, progress: float,
        gap: float) -> void:
    # Clear but unmistakably NOT a reward: six short coral ticks, no
    # white attack flash, green halo, or success particles.
    var fade: float = pow(1.0 - progress, 1.6)
    draw_circle(center, gap * (1.15 + progress * .9),
        Color(ERROR, .12 * fade))
    for index in range(6):
        var endpoint: Vector2 = particle_endpoint(center, gap,
            .18 + .42 * progress, index, 6)
        var ray: Vector2 = (endpoint - center).normalized()
        draw_line(endpoint - ray * gap * .46, endpoint,
            Color(ERROR, fade * .66), 2.0, true)

# A brief halo across the genuine measured staff lines. It stays behind the
# raster and only starts after a graded, physical MIDI note-on event.
func _staff_resonance(center: Vector2, gap: float,
        tone: Color, remaining: float) -> void:
    if staff_lines.is_empty():
        return
    var extent: float = gap * (3.4 + 2.1 * (1.0 - remaining))
    for normalized in staff_lines:
        var y: float = (float(normalized) - crop_origin.y) / crop_size.y * size.y
        if absf(y - center.y) > gap * 4.5:
            continue
        draw_line(Vector2(center.x - extent, y),
            Vector2(center.x + extent, y),
            Color(tone, .19 * remaining), 5.0, true)
        draw_line(Vector2(center.x - extent, y),
            Vector2(center.x + extent, y),
            Color(tone, .64 * remaining), 1.5, true)

func _draw() -> void:
    if hit_pulses.is_empty() and wrong_ghosts.is_empty() and preview_pulses.is_empty():
        return
    var now_ms: int = Time.get_ticks_msec()
    var gap: float = maxf(5.0, staff_gap_fraction * size.y)
    var radii: Vector2 = Ink.radii(gap)
    for index in range(maxi(0, hit_pulses.size() - MAX_VISIBLE_HITS),
            hit_pulses.size()):
        var hit: Dictionary = hit_pulses[index]
        if int(hit.get("page", -1)) != active_page:
            continue
        var remaining: float = _remaining(hit, now_ms, HIT_DURATION_MS)
        if remaining <= 0.0:
            continue
        var position: Vector2 = _sheet_position(hit)
        var tone: Color = HIT if str(hit.get("status", "")) == "on_time" else TIMING
        _success_impact(position, 1.0 - remaining, gap, radii, tone)
        _staff_resonance(position, gap, tone, remaining)

    # Blue-white preview impacts follow real metrical onsets and do not
    # imply success. They are separate from judged green MIDI pulses.
    for index in range(maxi(0, preview_pulses.size() - MAX_VISIBLE_HITS),
            preview_pulses.size()):
        var preview: Dictionary = preview_pulses[index]
        if int(preview.get("page", -1)) != active_page:
            continue
        var remaining: float = _remaining(preview, now_ms, 620)
        if remaining > 0.0:
            var center: Vector2 = _sheet_position(preview)
            _success_impact(center, 1.0 - remaining, gap, radii, PREVIEW)
            _staff_resonance(center, gap, PREVIEW, remaining)
    for index in range(maxi(0, wrong_ghosts.size() - MAX_VISIBLE_HITS),
            wrong_ghosts.size()):
        var wrong: Dictionary = wrong_ghosts[index]
        if int(wrong.get("page", -1)) != active_page:
            continue
        var remaining: float = _remaining(wrong, now_ms, ERROR_DURATION_MS)
        if remaining > 0.0:
            _error_impact(_sheet_position(wrong), 1.0 - remaining, gap)
