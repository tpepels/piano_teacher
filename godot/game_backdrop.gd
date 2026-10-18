extends Control

const Design := preload("res://practice_theme.gd")

# Quiet, hand-drawn background for the instrument view: no downloaded art,
# no UI occlusion, and no animation competing with the pianist's timing.
func _init() -> void:
    mouse_filter = Control.MOUSE_FILTER_IGNORE

func _draw() -> void:
    var w := size.x
    var h := size.y
    if w < 1 or h < 1:
        return
    # The score and library artwork supply the composition. A single quiet
    # forest field avoids decorative bands and console stripes behind them.
    draw_rect(Rect2(0, 0, w, h), Design.FOREST)
