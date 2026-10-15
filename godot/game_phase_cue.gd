extends Control

# A discreet transition cue. Every state and result comes from the backend;
# this script only animates presentation, never grading or progression.
const TEAL := Color("#9DECCA")
const AMBER := Color("#F0C18A")
const ERROR := Color("#F18E87")

var message := ""
var accent := TEAL
var opacity := 0.0
var target_opacity := 0.0
var last_key := ""
var onset := 0.0
var fading_message := ""
var fading_accent := TEAL
var fading_alpha := 0.0

func _init() -> void:
    mouse_filter = Control.MOUSE_FILTER_IGNORE
    focus_mode = Control.FOCUS_NONE
    clip_contents = true

func present(state: Dictionary) -> void:
    var phase: String = str(state.get("phase", "ready"))
    var mode: String = str(state.get("mode", "practice"))
    var result: Variant = state.get("take_result")
    var clean: bool = result is Dictionary and bool(result.get("clean", false))
    var next_message := ""
    var next_accent := TEAL
    match phase:
        "ready":
            next_message = ("PLAY A NOTE TO START" if not str(state.get("device", "")).is_empty()
                else "READY FOR PREVIEW")
        "count_in":
            next_message = "GET READY"
        "paused":
            next_message = "PAUSED"
            next_accent = AMBER
        "feedback":
            next_message = "CLEAN PASS" if clean else "RETRY"
            next_accent = TEAL if clean else ERROR
        "recovering":
            next_message = "SHORT RETRY"
            next_accent = AMBER
        "loading":
            next_message = "PREPARING"
            next_accent = AMBER
        "guided_complete":
            next_message = "IDEA COMPLETE"
        "performance_complete":
            next_message = "TAKE COMPLETE"
        "disconnected":
            next_message = "CONNECT PIANO"
            next_accent = AMBER
    if mode == "listen" and phase in ["ready", "feedback", "performance_complete"]:
        next_message = "LISTEN"
    # An empty library is not a playable Ready state.
    if not bool(state.get("loaded", false)):
        next_message = ""
    var key: String = "%s|%s|%s|%s" % [phase, mode, next_message,
        str(state.get("transport_id", -1))]
    if key != last_key:
        last_key = key
        onset = 0.0
        if next_message.is_empty() and not message.is_empty():
            fading_message = message
            fading_accent = accent
            fading_alpha = opacity
        elif not next_message.is_empty():
            fading_message = ""
            fading_alpha = 0.0
        # Only an actual phase change starts the entrance animation.
        opacity = minf(opacity, 0.55)
    message = next_message
    accent = next_accent
    target_opacity = 0.0 if message.is_empty() else 1.0
    queue_redraw()

func _process(delta: float) -> void:
    if not is_visible_in_tree():
        return
    var next_opacity: float = move_toward(opacity, target_opacity, delta * 7.0)
    if absf(next_opacity - opacity) > .0001:
        opacity = next_opacity
        queue_redraw()
    if onset < 1.0 and target_opacity > 0.0:
        onset = minf(1.0, onset + delta * 6.0)
        queue_redraw()
    if fading_alpha > 0.0:
        fading_alpha = maxf(0.0, fading_alpha - delta * 4.3)
        if fading_alpha <= .001:
            fading_message = ""
        queue_redraw()

func _draw() -> void:
    var rendered_text: String = message if not message.is_empty() else fading_message
    var rendered_alpha: float = opacity if not message.is_empty() else fading_alpha
    var rendered_tone: Color = accent if not message.is_empty() else fading_accent
    if rendered_text.is_empty() or rendered_alpha <= .001 or size.x < 25.0:
        return
    var font: Font = ThemeDB.fallback_font
    var font_size := 15
    var ink_width: float = font.get_string_size(rendered_text,
        HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x
    var bubble_width: float = minf(size.x - 2.0, ink_width + 31.0)
    var x: float = maxf(0.0, size.x - bubble_width - 1.0)
    var slide: float = (1.0 - onset) * 9.0
    var rect := Rect2(x + slide, 1.0, bubble_width, minf(size.y - 2.0, 32.0))
    draw_rect(rect, Color("#152B29", .83 * rendered_alpha))
    draw_rect(Rect2(rect.position, Vector2(2.0, rect.size.y)),
        Color(rendered_tone, rendered_alpha * .86))
    var baseline: float = rect.position.y + (rect.size.y +
        font.get_ascent(font_size) - font.get_descent(font_size)) * .5
    draw_string(font, Vector2(rect.position.x + 13.0, baseline),
        rendered_text, HORIZONTAL_ALIGNMENT_LEFT, rect.size.x - 18.0,
        font_size, Color("#EDF8EF", rendered_alpha))
