extends "res://notation/native/view.gd"
# Pixel intervention only: retain the exact score, layout and camera while
# hiding annotation paint, so subtraction cannot mistake reflow for a digit.
var show_fingerings := true

func _paint_fingerings(clock: float, playhead_x: float, gap: float) -> void:
    if show_fingerings:
        super._paint_fingerings(clock,playhead_x,gap)
