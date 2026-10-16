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
# Phase 7.8: visual beat is sampled from the Python-owned transport clock.
# This is lighting, not a second metronome or note-grading clock.
var beat_fraction := 0.0
var beat_in_bar := 0
var beats_per_bar := 4
var score_preview := false
var impact_age := 0.0
const AMBIENT_REDRAW_SECONDS := 1.0 / 30.0
var ambient_redraw_elapsed := 0.0

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

func sync_beat(beat: float, meter: int, preview: bool) -> void:
    # Called with the same extrapolated beat that drives score movement.
    # Freeze during pause; never create a separate animation transport.
    if not transport_active or not is_finite(beat):
        return
    var next_meter: int = clampi(meter, 1, 12)
    var next_fraction: float = fposmod(beat, 1.0)
    var next_bar: int = posmod(int(floor(beat)), next_meter)
    if (absf(beat_fraction - next_fraction) > .018
            or next_bar != beat_in_bar or next_meter != beats_per_bar
            or preview != score_preview):
        beat_fraction = next_fraction
        beat_in_bar = next_bar
        beats_per_bar = next_meter
        score_preview = preview
        queue_redraw()


func react(status: String) -> void:
    # Called only for assessed, fresh MIDI events. Preview never invokes it.
    impact_tone = ERROR if status == "unexpected" else (
        AURA if status == "on_time" else AMBER)
    impact_energy = minf(1.0, impact_energy + (
        .44 if status == "on_time" else .25))
    impact_age = 0.0
    queue_redraw()

func _process(delta: float) -> void:
    var redraw := false
    if absf(shown_progress - progress) > .0005:
        shown_progress = move_toward(shown_progress, progress, delta * .75)
        redraw = true
    if impact_energy > .001:
        impact_energy = maxf(0.0, impact_energy - delta * 1.6)
        impact_age = minf(1.0, impact_age + delta * 1.7)
        redraw = true
    if transport_active:
        breath = fposmod(breath + delta * .42, TAU)
        # Slow ambient breathing doesn't require a 60/144 Hz repaint of
        # the whole score panel. Short-lived MIDI impacts remain uncapped.
        ambient_redraw_elapsed += maxf(0.0, delta)
        if ambient_redraw_elapsed >= AMBIENT_REDRAW_SECONDS:
            ambient_redraw_elapsed = fposmod(
                ambient_redraw_elapsed, AMBIENT_REDRAW_SECONDS)
            redraw = true
    else:
        ambient_redraw_elapsed = 0.0
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
    # The playhead is at 42% of the viewport. All light stays behind
    # the actual score. During preview, beat motion is neutral: it does
    # not pretend a note has been struck or assessed correctly.
    var center := Vector2(w * .42, h * .51)
    var base_radius: float = minf(w, h) * .15
    var beat_attack: float = pow(1.0 - beat_fraction, 4.0) if transport_active else 0.0
    var pulse_tone: Color = Color("#91AFAB") if score_preview else AURA
    var ambient: float = (.028 + .010 * sin(breath) + beat_attack * .018
        if transport_active else .008)
    for i in range(12, 0, -1):
        var spread: float = float(i) / 12.0
        draw_circle(center, base_radius * (1.0 + spread * 3.2),
            Color(pulse_tone, ambient * (1.0 - spread) * .7))
    if transport_active:
        var x: float = center.x
        draw_line(Vector2(x, h * .17), Vector2(x, h * .83),
            Color(pulse_tone, .025 + .050 * beat_attack), 30.0, true)
        draw_line(Vector2(x, h * .26), Vector2(x, h * .74),
            Color(pulse_tone, .055 + .12 * beat_attack), 6.0, true)
        # A restrained metrical pulse below the score: no busy grid across
        # the notation and no duplicate click track.
        var gap: float = minf(17.0, maxf(7.0, w * .019))
        var group_left: float = center.x - float(beats_per_bar - 1) * gap * .5
        var pulse_y: float = h - 19.0
        for i in range(beats_per_bar):
            var selected: bool = i == beat_in_bar
            var p: Vector2 = Vector2(group_left + i * gap, pulse_y)
            if selected:
                draw_circle(p, 7.0 + beat_attack * 3.0,
                    Color(pulse_tone, .07 + beat_attack * .16))
            draw_circle(p, 2.4 + (1.4 * beat_attack if selected else 0.0),
                Color(pulse_tone if selected else Color("#66877F"),
                    (.60 + beat_attack * .36) if selected else .36))
    # Graded physical MIDI attacks create an unmistakable short-lived
    # colour burst. This code is called by the assessed-MIDI event path,
    # never by the beat clock, Listen, or ungraded preview.
    if impact_energy > .001:
        var expansion: float = 1.0 + impact_age * .58
        for i in range(10, 0, -1):
            var spread: float = float(i) / 10.0
            draw_circle(center, base_radius * expansion * (.9 + spread * 2.5),
                Color(impact_tone, impact_energy * (1.0 - spread) * .060))
        for i in range(12):
            var angle: float = TAU * float(i) / 12.0 + .23
            var ray: Vector2 = Vector2(cos(angle), sin(angle))
            var inner_radius: float = base_radius * (.45 + impact_age * 1.85)
            var ray_length: float = 4.0 + float(i % 4) * 2.0
            var origin: Vector2 = center + ray * inner_radius
            draw_line(origin, origin + ray * ray_length,
                Color(impact_tone, impact_energy * .69), 1.8, true)
            draw_circle(origin + ray * ray_length, 1.8,
                Color(impact_tone, impact_energy * .82))
    draw_line(Vector2(1, 1), Vector2(w - 1, 1), Color("#759D94", .13), 1.0)
    draw_rect(Rect2(1, h - 4, maxf(0, w - 2), 2), Color("#789B90", .18))
    if shown_progress > 0:
        var tip_x: float = 1.0 + (w - 2.0) * shown_progress
        draw_rect(Rect2(1, h - 4, maxf(0, tip_x - 1), 2), Color(accent, .92))
        draw_circle(Vector2(tip_x, h - 3), 5.0, Color(accent, .13))
        draw_circle(Vector2(tip_x, h - 3), 2.3, Color(accent, .95))
