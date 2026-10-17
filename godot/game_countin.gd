extends Control

# Phase 7.8: an easily readable preparation count without covering the
# moving score. Every numeral is derived from the backend's negative beat
# coordinate; no secondary timer can drift from the musical clock.
var count := 4
var current := -1
var beats_left := 0
var beat_fraction := 0.0

func _init() -> void:
    mouse_filter = Control.MOUSE_FILTER_IGNORE
    focus_mode = Control.FOCUS_NONE

func present(beat: float, beats_per_bar: int, running: bool, paused: bool) -> void:
    var show: bool = running and not paused and is_finite(beat) and beat < 0.0
    var next_count: int = clampi(beats_per_bar, 1, 12)
    var step: int = posmod(int(floor(beat + .00001)), next_count) if show else -1
    var fraction: float = fposmod(beat, 1.0) if show else 0.0
    var remaining: int = maxi(1, int(ceil(-beat - .00001))) if show else 0
    if (visible != show or count != next_count or current != step
            or beats_left != remaining or (show and absf(beat_fraction - fraction) > .012)):
        visible = show
        count = next_count
        current = step
        beats_left = remaining
        beat_fraction = fraction
        queue_redraw()

func _draw() -> void:
    if not visible or size.x < 70.0 or size.y < 20.0:
        return
    var y: float = size.y * .5
    var pulse: float = pow(1.0 - beat_fraction, 3.0)
    var numeral: String = str(beats_left)
    var font: Font = ThemeDB.fallback_font
    var font_size := 23
    var x: float = 21.0
    # The restrained halo makes the beat readable without covering
    # noteheads or implying that the learner earned a correct hit.
    draw_circle(Vector2(x, y), 18.0, Color("#58B58F", .10 + .12 * pulse))
    draw_arc(Vector2(x, y), 17.0, -.5 * PI,
        -.5 * PI + TAU * beat_fraction, 36,
        Color("#25866C", .78), 2.0, true)
    var numeral_width: float = font.get_string_size(
        numeral, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x
    var baseline: float = y + (
        font.get_ascent(font_size) - font.get_descent(font_size)) * .5
    draw_string(font, Vector2(x - numeral_width * .5, baseline),
        numeral, HORIZONTAL_ALIGNMENT_LEFT, -1,
        font_size, Color("#EAF4ED"))
    var space: float = maxf(6.0, (size.x - 64.0) / float(maxi(1, count)))
    var gap: float = minf(19.0, space)
    for i in range(count):
        var p: Vector2 = Vector2(56.0 + gap * i, y)
        draw_circle(p, 5.3, Color("#54756F", .86))
        draw_arc(p, 5.5, 0, TAU, 24,
            Color("#B2CFC0", .74), 1.0, true)
        if i == current:
            draw_circle(p, 7.0 + 3.0 * beat_fraction,
                Color("#48A87F", .12 + .24 * pulse))
            draw_circle(p, 3.9 + 1.1 * pulse, Color("#7BE8C0"))
        elif i < current:
            draw_circle(p, 2.8, Color("#4C9175"))
