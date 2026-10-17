extends Control

const Design := preload("res://practice_theme.gd")

# Phase 7.7c: the score remains the light source. These inexpensive canvas
# primitives are decorative only: no fake note hits in ungraded preview.
const AURA := Design.MINT
const ERROR := Design.CORAL
const AMBER := Design.AMBER

var phase := "ready"
var progress := 0.0
var shown_progress := 0.0
var progress_spark := 0.0
var milestone_slot := -1
var milestone_light := 0.0
var last_progress_session := ""
var accent := AURA
var transport_active := false
var breath := 0.0
var impact_energy := 0.0
var preview_energy := 0.0
var impact_tone := AURA
# Phase 7.8: visual beat is sampled from the Python-owned transport clock.
# This is lighting, not a second metronome or note-grading clock.
var beat_fraction := 0.0
var beat_in_bar := 0
var beats_per_bar := 4
var score_preview := false
var impact_age := 0.0
# One-shot result wave, keyed to the actual assessed take. Repeated /state
# polling cannot restart the animation or manufacture progress.
var last_result_key := ""
var result_wave := 0.0
var result_age := 0.0
var result_tone := Design.SCORE_ACCENT
const AMBIENT_REDRAW_SECONDS := 1.0 / 20.0
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
    if (bool(state.get("loaded", false))
            and not bool(state.get("preview_only", false))
            and str(state.get("mode", "")) in ["practice", "perform"]
            and next_phase == "feedback" and result is Dictionary):
        var result_key: String = "%s|%s|%s|%s" % [
            str(state.get("title", "")), str(state.get("transport_id", -1)),
            str(state.get("hand", "")), str(result.get("clean", false))]
        if result_key != last_result_key:
            last_result_key = result_key
            result_tone = Design.SCORE_ACCENT if bool(result.get("clean", false)) else Color("#BC5A50")
            result_age = 0.0
            result_wave = 1.0
            queue_redraw()
    var earned_milestone: bool = bool(state.get("loaded", false)) and not bool(
        state.get("preview_only", false)) and str(state.get("mode", "")) in [
        "practice", "perform"] and next_phase in ["playing", "feedback"]
    var earlier_slot: int = clampi(int(floor(progress * 5.0 + .00001)), 0, 5)
    var latest_slot: int = clampi(int(floor(next_progress * 5.0 + .00001)), 0, 5)
    var session_key: String = "%s|%s|%s" % [
        str(state.get("revision", -1)), str(state.get("transport_id", -1)),
        str(state.get("hand", ""))]
    if session_key != last_progress_session:
        last_progress_session = session_key
        shown_progress = next_progress
        progress_spark = 0.0
        milestone_slot = -1
        milestone_light = 0.0
    elif earned_milestone and latest_slot > earlier_slot:
        milestone_slot = maxi(0, mini(4, latest_slot - 1))
        milestone_light = 1.0
        progress_spark = 1.0
        queue_redraw()
    elif next_progress > progress + .04 and next_progress >= shown_progress:
        # This is the backend's actual progress, never a simulated reward.
        progress_spark = 1.0
    if next_progress < progress - .08:
        shown_progress = next_progress
        progress_spark = 0.0
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
    # Store the latest clock each frame; redraw on metrical changes or at
    # the stage's 20 Hz ambient cadence in _process. Previously every
    # ~0.018 beat triggered another redraw, defeating the frame cap.
    var structural_change: bool = next_bar != beat_in_bar or \
        next_meter != beats_per_bar or preview != score_preview
    beat_fraction = next_fraction
    beat_in_bar = next_bar
    beats_per_bar = next_meter
    score_preview = preview
    if structural_change:
        queue_redraw()


func preview_react() -> void:
    # Neutral blue metrical arrival - never a graded success effect.
    preview_energy = minf(.85, preview_energy + .48)
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
        shown_progress = move_toward(shown_progress, progress, delta * .9)
        redraw = true
    if progress_spark > .001:
        progress_spark = maxf(0.0, progress_spark - delta * 2.8)
        redraw = true
    if milestone_light > .001:
        milestone_light = maxf(0.0, milestone_light - delta * 1.7)
        redraw = true
    if preview_energy > .001:
        preview_energy = maxf(0.0, preview_energy - delta * 1.15)
        redraw = true
    if impact_energy > .001:
        impact_energy = maxf(0.0, impact_energy - delta * 1.6)
        impact_age = minf(1.0, impact_age + delta * 1.7)
        redraw = true
    if result_wave > .001:
        result_wave = maxf(0.0, result_wave - maxf(0.0, delta) * .86)
        result_age = minf(1.0, result_age + maxf(0.0, delta) * .86)
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
    # One stage fill rather than 32 full-width alpha bands per frame.
    # This dramatically reduces overdraw at 2880x1800 / HiDPI.
    draw_rect(Rect2(0, 0, w, h), Design.STAGE)
    # The playhead is at 42% of the viewport. All light stays behind
    # the actual score. During preview, beat motion is neutral: it does
    # not pretend a note has been struck or assessed correctly.
    var center := Vector2(w * .42, h * .51)
    var base_radius: float = minf(w, h) * .15
    var beat_attack: float = pow(1.0 - beat_fraction, 4.0) if transport_active else 0.0
    var pulse_tone: Color = Color("#5D8AA6") if score_preview else Design.SCORE_ACCENT
    var ambient: float = (.035 + .014 * sin(breath) + beat_attack * .045
        if transport_active else .008)
    # Three diffuse rings give a softer cinematic glow with far less
    # translucent overdraw than twelve stacked screen-scale discs.
    for i in range(3, 0, -1):
        var spread: float = float(i) / 3.0
        draw_circle(center, base_radius * (1.0 + spread * 1.3),
            Color(pulse_tone, ambient * (1.0 - spread) * .27))
    if transport_active:
        var x: float = center.x
        draw_line(Vector2(x, h * .17), Vector2(x, h * .83),
            Color(pulse_tone, .035 + .085 * beat_attack), 28.0, true)
        draw_line(Vector2(x, h * .26), Vector2(x, h * .74),
            Color(pulse_tone, .09 + .16 * beat_attack), 7.0, true)
        # A restrained metrical pulse below the score: no busy grid across
        # the notation and no duplicate click track.
        var gap: float = minf(17.0, maxf(7.0, w * .019))
        var group_left: float = center.x - float(beats_per_bar - 1) * gap * .5
        var pulse_y: float = h - 43.0
        for i in range(beats_per_bar):
            var selected: bool = i == beat_in_bar
            var p: Vector2 = Vector2(group_left + i * gap, pulse_y)
            if selected:
                draw_circle(p, 7.0 + beat_attack * 3.0,
                    Color(pulse_tone, .07 + beat_attack * .16))
            draw_circle(p, 2.4 + (1.4 * beat_attack if selected else 0.0),
                Color(pulse_tone if selected else Color("#A4B7A9"),
                    (.64 + beat_attack * .36) if selected else .58))
    # Physical MIDI affects the green/coral scored energy. A preview note
    # creates blue energy through an independent, explicitly ungraded path.
    var drawn_energy: float = maxf(impact_energy, preview_energy)
    var drawn_tone: Color = (Design.SCORE_ACCENT if impact_energy > preview_energy
        and impact_tone == AURA else Color("#C05A51") if impact_energy > preview_energy
        and impact_tone == ERROR else Color("#A98240") if impact_energy > preview_energy
        else Color("#477CA6"))
    if drawn_energy > .001:
        var expansion: float = 1.0 + impact_age * .58
        for i in range(3, 0, -1):
            var spread: float = float(i) / 3.0
            draw_circle(center, base_radius * expansion * (.9 + spread * 1.6),
                Color(drawn_tone, drawn_energy * (1.0 - spread) * .13))
        for i in range(12):
            var angle: float = TAU * float(i) / 12.0 + .23
            var ray: Vector2 = Vector2(cos(angle), sin(angle))
            var inner_radius: float = base_radius * (.45 + impact_age * 1.85)
            var ray_length: float = 4.0 + float(i % 4) * 2.0
            var origin: Vector2 = center + ray * inner_radius
            draw_line(origin, origin + ray * ray_length,
                Color(drawn_tone, drawn_energy * .84), 1.8, true)
            draw_circle(origin + ray * ray_length, 1.8,
                Color(drawn_tone, drawn_energy * .92))
    # Clean takes generate an instrument-wide wave from the playhead;
    # retries have a softer coral wash. It is drawn *behind* engraved
    # notation and disappears after the one-shot result transition.
    if result_wave > .001:
        var sweep: float = result_age * 1.4
        var energy: float = result_wave * result_wave
        var spread_px: float = minf(w * .62, w * (.10 + sweep * .53))
        var left_x: float = maxf(0.0, center.x - spread_px)
        var right_x: float = minf(w, center.x + spread_px)
        for band in range(8):
            var height_offset: float = float(band) * 3.4
            draw_line(Vector2(left_x, h - 4.0 - height_offset),
                Vector2(right_x, h - 4.0 - height_offset),
                Color(result_tone, energy * (.14 - .014 * band)),
                1.8 + float(7 - band) * .75, true)
        for arc in range(3):
            var radius: float = base_radius * (.85 + sweep * 2.1 + float(arc) * .16)
            draw_arc(center, radius, PI * .11, PI * .89, 48,
                Color(result_tone, energy * (.28 - .07 * arc)), 1.6, true)
            draw_arc(center, radius, PI * 1.11, PI * 1.89, 48,
                Color(result_tone, energy * (.28 - .07 * arc)), 1.6, true)
    # Moodboard: five separated progress measures below the score, not a
    # thin anonymous browser-style loading bar. The backend is authoritative.
    draw_line(Vector2(1, 1), Vector2(w-1, 1), Color("#ADC3B4", .36), 1.0)
    var slots := 5
    var inset: float = clampf(w * .045, 15.0, 58.0)
    var spacing: float = 7.0
    var rail_width: float = maxf(1.0, w - inset * 2.0)
    var segment: float = maxf(1.0, (rail_width - spacing * float(slots-1)) / float(slots))
    var track_y: float = h - 20.0
    for i in range(slots):
        var left: float = inset + float(i) * (segment + spacing)
        var amount: float = clampf(shown_progress * float(slots) - float(i), 0.0, 1.0)
        draw_rect(Rect2(left, track_y, segment, 7.0),
            Color("#DDE7DF"), true)
        if amount > .0001:
            draw_rect(Rect2(left, track_y, segment * amount, 7.0),
                Color(Design.SCORE_PROGRESS, .89 + progress_spark * .1), true)
        # One quick gold-toned glint for a *backend-confirmed* fifth
        # milestone. Never triggered by Listen or keyboard-free preview.
        if i == milestone_slot and milestone_light > .001:
            var glint: float = milestone_light * milestone_light
            var sweep_x: float = left + segment * (1.0 - milestone_light)
            draw_line(Vector2(left, track_y - 2.0),
                Vector2(left + segment, track_y - 2.0),
                Color("#BCA06A", glint * .34), 2.0, true)
            draw_circle(Vector2(sweep_x, track_y + 3.0),
                7.0 + (1.0 - milestone_light) * 3.0,
                Color("#C9A96B", glint * .14))
            draw_circle(Vector2(sweep_x, track_y + 3.0),
                2.6, Color("#B89A62", glint * .8))
    if progress_spark > .001 and shown_progress > .001:
        var spot: float = inset + rail_width * shown_progress
        draw_circle(Vector2(spot, track_y + 3.5),
            13.0 * progress_spark, Color(Design.SCORE_ACCENT, .12 * progress_spark))
        draw_circle(Vector2(spot, track_y + 3.5), 3.5,
            Color(Design.SCORE_ACCENT, .86 * progress_spark))
    # A crisp, small green "play here" flag follows the *existing* fixed
    # timing rule. It has no independent musical clock or grading state.
    if transport_active:
        var flag_width := 90.0
        var flag_height := 25.0
        var x: float = clampf(center.x - flag_width * .5, 5.0,
            maxf(5.0, w - flag_width - 5.0))
        var top_y: float = maxf(6.0, h * .09)
        var flag := Rect2(x, top_y, flag_width, flag_height)
        draw_rect(flag, Color("#295B49"))
        draw_colored_polygon(PackedVector2Array([
            Vector2(center.x - 5.0, flag.end.y),
            Vector2(center.x + 5.0, flag.end.y),
            Vector2(center.x, flag.end.y + 6.0)]), Color("#295B49"))
        var font: Font = ThemeDB.fallback_font
        var text: String = "FOLLOW" if score_preview else "PLAY HERE"
        var font_size := 13
        var ink_width: float = font.get_string_size(text,
            HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x
        draw_string(font, Vector2(center.x - ink_width * .5,
            flag.position.y + 17.0), text, HORIZONTAL_ALIGNMENT_LEFT,
            -1, font_size, Color("#F6FBF6"))
