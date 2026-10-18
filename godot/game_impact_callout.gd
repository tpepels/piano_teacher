extends Control

# Compact, event-driven coaching. MIDI assessment is authoritative; this
# component never listens to the transport clock or decides whether a note
# was correct. Animates for <700 ms and sleeps while idle.
const Design := preload("res://practice_theme.gd")
const DURATION := .66
const REPEAT_GUARD_MS := 115

var message := ""
var subtext := ""
var tone := Design.SCORE_ACCENT
var elapsed := DURATION
var last_status := ""
var last_trigger_ms := -10000

func _init() -> void:
    mouse_filter = Control.MOUSE_FILTER_IGNORE
    focus_mode = Control.FOCUS_NONE
    custom_minimum_size = Vector2(226, 58)

func react(status: String, now_ms: int = -1) -> void:
    var stamp: int = Time.get_ticks_msec() if now_ms < 0 else now_ms
    if status == last_status and stamp-last_trigger_ms < REPEAT_GUARD_MS:
        return # A chord is one musical event, not six competing banners.
    match status:
        "on_time":
            message = "RIGHT ON TIME"
            subtext = "Keep the rhythm flowing"
            tone = Design.SCORE_ACCENT
        "early":
            message = "A LITTLE EARLY"
            subtext = "Wait for the beat"
            tone = Color("#A4773A")
        "late":
            message = "A LITTLE LATE"
            subtext = "Meet the playhead"
            tone = Color("#A4773A")
        "unexpected":
            message = "TRY THAT NOTE"
            subtext = "Follow the highlighted pitch"
            tone = Color("#BD6157")
        _:
            return
    last_trigger_ms = stamp
    last_status = status
    elapsed = 0.0
    queue_redraw()

func clear() -> void:
    if elapsed < DURATION:
        elapsed = DURATION
        queue_redraw()
    last_status = ""

func _process(delta: float) -> void:
    if elapsed >= DURATION:
        return
    elapsed = minf(DURATION, elapsed + maxf(0.0, delta))
    queue_redraw()

func _draw() -> void:
    if elapsed >= DURATION or size.x < 155.0 or size.y < 42.0:
        return
    var t: float = clampf(elapsed/DURATION, 0.0, 1.0)
    # One quick rise, then a fade and gentle settling movement.
    var entry: float = 1.0-pow(1.0-minf(t/.24, 1.0), 3.0)
    var fade: float = minf(1.0, (1.0-t)/.24)
    var alpha: float = fade*minf(1.0, entry*2.0)
    if alpha <= .001:
        return
    # Quick overshoot and settle rather than a flat notification slide.
    # This remains a brief local effect, not a fullscreen animation.
    var overshoot: float = sin(PI * minf(1.0, t/.33)) * 3.0
    var lift: float = (1.0-entry)*11.0 - overshoot
    var rect := Rect2(Vector2((1.0-entry)*18.0, 1.0 + lift),
        size-Vector2(18, 5))
    var radius: float = minf(13.0, rect.size.y*.26)
    var paper := Color("#203D3A", alpha*.96)
    draw_rect(Rect2(rect.position.x+radius, rect.position.y,
        rect.size.x-2*radius, rect.size.y), paper)
    draw_circle(rect.position+Vector2(radius, radius), radius, paper)
    draw_circle(Vector2(rect.end.x-radius, rect.position.y+radius), radius, paper)
    draw_rect(Rect2(rect.position.x, rect.position.y+radius,
        rect.size.x, rect.size.y-2*radius), paper)
    draw_circle(Vector2(rect.position.x+radius,rect.end.y-radius),radius,paper)
    draw_circle(rect.end-Vector2(radius,radius),radius,paper)
    # Meaning is expressed through an instrument-colored left accent,
    # without covering the score or creating a bright full-screen flash.
    draw_line(rect.position+Vector2(5, 9),Vector2(rect.position.x+5,rect.end.y-9),
        Color(tone,alpha*.95),4.0,true)
    # Small leading impact token echoes the note reaction without spawning
    # particles or hiding any musical symbols.
    var token := rect.position + Vector2(19, rect.size.y*.47)
    var burst: float = pow(1.0 - minf(1.0, t/.33), 1.7)
    draw_circle(token, 7.0 + 6.0 * burst, Color(tone,.13*alpha*burst))
    draw_arc(token, 5.2 + burst*6.0, 0, TAU, 24,
        Color(tone,.73*alpha), 1.8, true)
    var font: Font = get_theme_font("font")
    var main_size := 19
    var small_size := 14
    var baseline := rect.position.y + 24.0
    draw_string(font,Vector2(rect.position.x+36,baseline),message,
        HORIZONTAL_ALIGNMENT_LEFT,maxf(10.0,rect.size.x-49),main_size,
        Color("#EBF9EF",alpha))
    draw_string(font,Vector2(rect.position.x+36,baseline+18),subtext,
        HORIZONTAL_ALIGNMENT_LEFT,maxf(10.0,rect.size.x-49),small_size,
        Color("#B3D6C5",alpha))
    # Small expressive sparkle at the top edge, not sixteen independent
    # full-screen particle nodes.
    var spark: float = pow(1.0-t,2.0)
    if spark > .001:
        var p := Vector2(rect.end.x-12,rect.position.y+5)
        draw_circle(p,2.0+3.0*spark,Color(tone,.40*alpha*spark))
        draw_line(p+Vector2(-8,0),p+Vector2(-4-3*spark,0),
            Color(tone,alpha*spark),1.3,true)
