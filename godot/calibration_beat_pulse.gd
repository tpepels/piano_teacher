extends Control
## Live pulse for one preparation followed by uninterrupted calibration taps.
## The application supplies the same projected beat used for click playback.
var beat := -1.0
var round_beats := 8
var count_in := 4

func _init() -> void:
    mouse_filter = Control.MOUSE_FILTER_IGNORE
    custom_minimum_size = Vector2(108, 102)
    visible = false

func present_beat(at_beat: float, is_active: bool,
        per_round: int = 8, preparation: int = 4) -> void:
    round_beats = maxi(1, per_round)
    count_in = maxi(0, preparation)
    beat = at_beat
    visible = is_active
    if is_active:
        queue_redraw()

func is_preparing() -> bool:
    # Preparation occurs once, not at the boundary of every eight-tap round.
    return beat < float(count_in)

func _draw() -> void:
    if not visible:
        return
    var middle := Vector2(52, 49)
    var preparing := is_preparing()
    var phase := fposmod(beat, 1.0)
    var inhale := pow(1.0-phase, 2.4)
    var tone := Color("#B9CCBF") if preparing else Color("#75DDB4")
    draw_circle(middle, 34.0, Color(tone, .075))
    draw_circle(middle, 15.0+16.0*inhale, Color(tone, .16+.11*inhale))
    draw_arc(middle, 18.0+16.0*inhale, 0.0, TAU, 64,
        Color(tone, .65+.30*inhale), 2.8, true)
    draw_circle(middle, 7.0+7.0*inhale, Color(tone, .92))
    var text_value := "COUNT" if preparing else "PLAY"
    var font := ThemeDB.fallback_font
    var width := font.get_string_size(text_value,
        HORIZONTAL_ALIGNMENT_LEFT, -1, 12).x
    draw_string(font, middle+Vector2(-width*.5, 48),
        text_value, HORIZONTAL_ALIGNMENT_LEFT, -1, 12, tone)
