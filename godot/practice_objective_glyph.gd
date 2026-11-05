extends Control
## Small native vector target, matching the Practice moodboard objective card.
## No image assets and no additional application state.
const Design := preload("res://practice_theme.gd")

func _init() -> void:
    mouse_filter = Control.MOUSE_FILTER_IGNORE
    custom_minimum_size = Vector2(31,31)
    size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
    size_flags_vertical = Control.SIZE_SHRINK_CENTER

func _draw() -> void:
    var center := size*.5
    draw_circle(center,15.0,Color(Design.MINT,.11))
    draw_arc(center,11.0,-PI*.48,PI*1.38,42,
        Color(Design.MINT,.82),2.0,true)
    draw_arc(center,6.0,0.0,TAU,32,
        Color(Design.HIGHLIGHT,.91),1.8,true)
    draw_circle(center,2.0,Design.HIGHLIGHT)
    draw_line(center+Vector2(5,-5),center+Vector2(12,-12),
        Design.HIGHLIGHT,1.6,true)
