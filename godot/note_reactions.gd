extends Control

# Brief, glyph-aligned feedback behind the original Verovio notation.
# Colour distinguishes assessed MIDI from neutral, ungraded preview without
# particles, expanding halos or additional pitch glyphs.
const Ink := preload("res://notehead_ink.gd")
const Design := preload("res://practice_theme.gd")
const HIT := Design.SCORE_ACCENT
const TIMING := Design.AMBER
const ERROR := Design.CORAL
const PREVIEW := Design.SLATE
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
    # Gentle pigment stays beneath the actual engraved notehead.
    var bloom_material := CanvasItemMaterial.new()
    # Normal blending keeps preview neutral on the charcoal score surface.
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
    var fade: float = pow(1.0 - progress, 1.4)
    var preview: bool = tone == PREVIEW
    var outline: Vector2 = radii * (1.10 + progress * .06)
    draw_polyline(Ink.ellipse(center, outline.x, outline.y),
        Color(tone, fade * (.32 if preview else .62)),
        1.0 if preview else 1.5, true)

func _error_impact(center: Vector2, progress: float,
        gap: float) -> void:
    var fade: float = pow(1.0 - progress, 1.5)
    var radii: Vector2 = Ink.radii(gap) * 1.14
    draw_polyline(Ink.ellipse(center, radii.x, radii.y),
        Color(ERROR, .66 * fade), 1.5, true)

func _staff_resonance(_center: Vector2, _gap: float,
        _tone: Color, _remaining: float) -> void:
    # Retained for callers; assessed feedback is confined to the real note.
    pass

func _draw() -> void:
    if hit_pulses.is_empty() and wrong_ghosts.is_empty() and preview_pulses.is_empty():
        return
    var now_ms: int = Time.get_ticks_msec()
    var gap: float = maxf(5.0, staff_gap_fraction * size.y)
    var radii: Vector2 = Ink.radii(gap)
    # Successful and preview notes use a single short, glyph-aligned light
    # pulse in ScoreOverlay (foreground). Rendering another halo behind the
    # raster doubled the glow and made it appear detached from the notehead.
    # This canvas retains only red correction contours for wrong notes.
    for index in range(maxi(0, wrong_ghosts.size() - MAX_VISIBLE_HITS),
            wrong_ghosts.size()):
        var wrong: Dictionary = wrong_ghosts[index]
        if int(wrong.get("page", -1)) != active_page:
            continue
        var remaining: float = _remaining(wrong, now_ms, ERROR_DURATION_MS)
        if remaining > 0.0:
            _error_impact(_sheet_position(wrong), 1.0 - remaining, gap)
