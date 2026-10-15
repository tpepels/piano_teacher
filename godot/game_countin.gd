extends Control

# Small rhythmic preparation lights. The engine's beat clock remains the
# authority: no independent countdown clock or grading logic.
var count := 4
var current := -1
var beat_fraction := 0.0

func _init() -> void:
    mouse_filter = Control.MOUSE_FILTER_IGNORE
    focus_mode = Control.FOCUS_NONE

func present(beat: float, beats_per_bar: int, running: bool, paused: bool) -> void:
    var step := posmod(int(floor(beat + .00001)), maxi(1, beats_per_bar))
    var show := running and not paused and beat < 0.0
    var next_count := clampi(beats_per_bar, 1, 8)
    var fraction := beat - floor(beat)
    if visible != show or count != next_count or (show and current != step) or (show and absf(beat_fraction - fraction) > 0.01):
        visible = show
        count = next_count
        current = step
        beat_fraction = fraction
        queue_redraw()

func _draw() -> void:
    var gap := minf(24.0, (size.x - 12.0) / float(maxi(1, count)))
    for i in range(count):
        var center := Vector2(8.0 + gap * i, size.y * .5)
        draw_circle(center, 6.5, Color("#385C56"))
        draw_arc(center, 7.0, 0, TAU, 20, Color("#72A798"), 1.0, true)
        if i == current:
            var attack := 1.0 - beat_fraction
            draw_circle(center, 9.0 + 6.0 * beat_fraction, Color("#82ECC7", .08 + .23 * attack))
            draw_circle(center, 5.3 + 1.4 * attack, Color("#9FF7D7"))
        elif i < current:
            draw_circle(center, 3.6, Color("#79BBA4"))
