extends Control

# Quiet, hand-drawn background for the instrument view: no downloaded art,
# no UI occlusion, and no animation competing with the pianist's timing.
func _init() -> void:
    mouse_filter = Control.MOUSE_FILTER_IGNORE

func _draw() -> void:
    var w := size.x
    var h := size.y
    if w < 1 or h < 1:
        return
    for i in range(40):
        var frac := float(i) / 39.0
        var color := Color("#0C1519").lerp(Color("#122723"), 1.0 - frac)
        draw_rect(Rect2(0, h * i / 40.0, w, h / 40.0 + 1), color)
    # Thin architectural lines suggest a musical console without imitating
    # an interactive note lane or interfering with the score.
    for k in range(1, 6):
        var x: float = w * float(k) / 6.0
        draw_line(Vector2(x, 0), Vector2(x - 85, h),
            Color("#4C9987", .022), 1.0)
    draw_rect(Rect2(0, 0, w, 3), Color("#5BDFB6", .18))
