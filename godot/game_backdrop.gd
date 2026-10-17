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
    # Static, subtle stage background; fewer overdraw bands.
    for i in range(16):
        var frac := float(i) / 15.0
        var color: Color = Design.FOREST.lerp(Design.PANEL_RECESSED, 1.0 - frac)
        draw_rect(Rect2(0, h * i / 16.0, w, h / 16.0 + 1), color)
    # Thin architectural lines suggest a musical console without imitating
    # an interactive note lane or interfering with the score.
    for k in range(1, 6):
        var x: float = w * float(k) / 6.0
        draw_line(Vector2(x, 0), Vector2(x - 85, h),
            Color(Design.SAGE, .025), 1.0)
    draw_rect(Rect2(0, 0, w, 2), Color(Design.TEAL, .22))
