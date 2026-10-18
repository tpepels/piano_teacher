extends Control

const Design := preload("res://practice_theme.gd")

# A quiet score canvas and five-part musical progress rail. All state comes
# from the existing transport; preview never creates graded feedback.
const AURA := Design.MINT
const ERROR := Design.CORAL
const AMBER := Design.AMBER

# The illuminated playing lane follows the actual measured staff geometry.
# There is no alternative sheet renderer and no second timing source.
var staff_band_top := .28
var staff_band_bottom := .80
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

func set_staff_band(first_line_fraction: float, last_line_fraction: float) -> void:
    var top: float = clampf(first_line_fraction, .06, .90)
    var bottom: float = clampf(last_line_fraction, top + .02, .94)
    if absf(top - staff_band_top) > .003 or absf(bottom - staff_band_bottom) > .003:
        staff_band_top = top
        staff_band_bottom = bottom
        queue_redraw()

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
    # Neutral metrical arrival - never a graded success effect.
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
    # Keep the notation on one calm surface. Its real score overlay owns the
    # precise timing line; this narrow underlay adds only a restrained edge.
    draw_rect(Rect2(0, 0, w, h), Design.STAGE)
    if transport_active or phase == "paused":
        var x: float = w * .42
        var top: float = maxf(8.0, staff_band_top * h - 18.0)
        var bottom: float = minf(h - 32.0, staff_band_bottom * h + 18.0)
        if bottom > top:
            draw_line(Vector2(x, top), Vector2(x, bottom),
                Color(Design.SCORE_ACCENT, .065), 6.0, true)
            draw_line(Vector2(x, top), Vector2(x, bottom),
                Color(Design.SCORE_ACCENT, .20), 1.0, true)
        if transport_active and staff_band_top * h >= 40.0:
            # A small reference label matches the moodboard, without a
            # travelling effect or an opaque banner across the notation.
            var flag_width := 78.0
            var flag_height := 22.0
            var flag_x: float = clampf(x - flag_width * .5, 5.0,
                maxf(5.0, w - flag_width - 5.0))
            var flag_y := 4.0
            var flag := Rect2(flag_x, flag_y, flag_width, flag_height)
            var body := StyleBoxFlat.new()
            body.bg_color = Color(Design.PINE, .96)
            body.set_corner_radius_all(7)
            draw_style_box(body, flag)
            var font: Font = ThemeDB.fallback_font
            var text: String = "Follow" if score_preview else "Play here"
            var font_size := 12
            var ink_width: float = font.get_string_size(text,
                HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x
            draw_string(font, Vector2(flag.get_center().x - ink_width * .5,
                flag.position.y + 15.0), text, HORIZONTAL_ALIGNMENT_LEFT,
                -1, font_size, Design.STONE)

    # The moodboard's five quiet progress measures remain readable beneath
    # the score. Remaining music is sage, rather than bright notation ink.
    var slots := 5
    var inset: float = clampf(w * .045, 15.0, 58.0)
    var spacing: float = 7.0
    var rail_width: float = maxf(1.0, w - inset * 2.0)
    var segment: float = maxf(1.0, (rail_width - spacing * float(slots-1)) / float(slots))
    var track_y: float = h - 20.0
    var fill_tone: Color = Design.SCORE_PROGRESS
    # A confirmed take may gently tint its rail, without washing the music
    # in colour or sending a celebration across the staff.
    if result_wave > .001:
        fill_tone = fill_tone.lerp(result_tone, result_wave * .18)
    for i in range(slots):
        var left: float = inset + float(i) * (segment + spacing)
        var amount: float = clampf(shown_progress * float(slots) - float(i), 0.0, 1.0)
        draw_rect(Rect2(left, track_y, segment, 7.0), Color(Design.SAGE, .58), true)
        if amount > .0001:
            draw_rect(Rect2(left, track_y, segment * amount, 7.0),
                Color(fill_tone, .84 + progress_spark * .08), true)
        if i == milestone_slot and milestone_light > .001:
            draw_line(Vector2(left, track_y + 1.0),
                Vector2(left + segment, track_y + 1.0),
                Color(Design.SCORE_PROGRESS, milestone_light * .22), 1.0, true)
