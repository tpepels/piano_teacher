extends Control

# Phase 7.7c: the score remains the light source. These inexpensive canvas
# primitives are decorative only: no fake note hits in ungraded preview.
const AURA := Color("#69E2BF")
const ERROR := Color("#EF7776")
const AMBER := Color("#F0BC76")

var phase := "ready"
var progress := 0.0
var shown_progress := 0.0
var accent := AURA
var transport_active := false
var breath := 0.0
var impact_energy := 0.0
var impact_tone := AURA

func _init() -> void:
    mouse_filter = Control.MOUSE_FILTER_IGNORE
    focus_mode = Control.FOCUS_NONE

func present(state: Dictionary) -> void:
    var next_phase: String = str(state.get("phase", "ready"))
    var next_progress: float = clampf(float(state.get("progress", 0.0)), 0.0, 1.0)
    var next_active: bool = next_phase in ["playing", "count_in"] and (
        bool(state.get("running", false)) and not bool(state.get("paused", false)))
    var result: Variant = state.get("take_result")
    var failed_take: bool = result is Dictionary and not bool(result.get("clean", false))
    var next_accent: Color = (
        ERROR if next_phase == "feedback" and failed_take
        else AMBER if next_phase in ["paused", "recovering"]
        else AURA)
    if next_progress < progress - .08:
        shown_progress = next_progress
    if phase != next_phase or absf(next_progress-progress) > .003 \
            or accent != next_accent or transport_active != next_active:
        phase = next_phase
        progress = next_progress
        accent = next_accent
        transport_active = next_active
        queue_redraw()

func react(status: String) -> void:
    # Called only for assessed, fresh MIDI events. Preview never invokes it.
    impact_tone = ERROR if status == "unexpected" else (
        AURA if status == "on_time" else AMBER)
    impact_energy = minf(1.0, impact_energy + (
        .44 if status == "on_time" else .25))
    queue_redraw()

func _process(delta: float) -> void:
    var redraw := false
    if absf(shown_progress - progress) > .0005:
        shown_progress = move_toward(shown_progress, progress, delta * .75)
        redraw = true
    if impact_energy > .001:
        impact_energy = maxf(0.0, impact_energy - delta * 2.0)
        redraw = true
    if transport_active:
        breath = fposmod(breath + delta * .42, TAU)
        redraw = true
    if redraw:
        queue_redraw()

func _draw() -> void:
    var w: float = size.x
    var h: float = size.y
    if w < 1 or h < 1:
        return
    for i in range(32):
        var y: float = h * float(i) / 32.0
        var lift: float = 1.0 - absf(float(i) - 14.0) / 25.0
        draw_rect(Rect2(0, y, w, h / 32.0 + 1.0),
            Color("#101B1D").lerp(Color("#1A2929"),
                clampf(lift * .75, 0.0, 1.0)))
    # Gentle breathing while the transport plays, including MIDI-free
    # preview and Listen; never imply that a note was played correctly.
    var ambient: float = (.026 + .009 * sin(breath)) if transport_active else .008
    var center := Vector2(w * .42, h * .51)
    var base_radius: float = minf(w, h) * .15
    for i in range(12, 0, -1):
        var spread: float = float(i) / 12.0
        draw_circle(center, base_radius * (1.0 + spread * 3.2),
            Color(AURA, ambient * (1.0 - spread) * .7))
    if transport_active:
        var x: float = center.x
        draw_line(Vector2(x, h * .17), Vector2(x, h * .83),
            Color(AURA, .022), 30.0, true)
        draw_line(Vector2(x, h * .26), Vector2(x, h * .74),
            Color(AURA, .045), 7.0, true)
    # Strong music-responsive studio light, behind the notation.
    if impact_energy > .001:
        for i in range(10, 0, -1):
            var spread: float = float(i) / 10.0
            draw_circle(center, base_radius * (.9 + spread * 2.5),
                Color(impact_tone, impact_energy * (1.0 - spread) * .045))
    draw_line(Vector2(1, 1), Vector2(w - 1, 1), Color("#759D94", .13), 1.0)
    draw_rect(Rect2(1, h - 4, maxf(0, w - 2), 2), Color("#789B90", .18))
    if shown_progress > 0:
        var tip_x: float = 1.0 + (w - 2.0) * shown_progress
        draw_rect(Rect2(1, h - 4, maxf(0, tip_x - 1), 2), Color(accent, .92))
        draw_circle(Vector2(tip_x, h - 3), 5.0, Color(accent, .13))
        draw_circle(Vector2(tip_x, h - 3), 2.3, Color(accent, .95))
