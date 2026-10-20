extends Control

const Design := preload("res://practice_theme.gd")

# Broad canopy light and distant silhouettes reinterpret the moodboards.
# Generated once; the score supplies the motion, with no idle frame loop.
var light: GradientTexture2D

func _init() -> void:
    mouse_filter = Control.MOUSE_FILTER_IGNORE
    var gradient := Gradient.new()
    gradient.colors = PackedColorArray([Design.CANOPY, Design.NIGHT])
    light = GradientTexture2D.new()
    light.gradient = gradient
    light.width = 512
    light.height = 512
    light.fill = GradientTexture2D.FILL_RADIAL
    light.fill_from = Vector2(.42, .28)
    light.fill_to = Vector2(.95, .95)
    resized.connect(queue_redraw)

func _draw() -> void:
    var w := size.x
    var h := size.y
    if w < 1 or h < 1:
        return
    draw_texture_rect(light, Rect2(Vector2.ZERO, size), false)
    # Low silhouettes sit below the reading field. No borrowed board art.
    draw_colored_polygon(PackedVector2Array([
        Vector2(0,h*.88), Vector2(w*.12,h*.76), Vector2(w*.25,h*.89),
        Vector2(w*.43,h*.73), Vector2(w*.60,h*.88), Vector2(w*.81,h*.74),
        Vector2(w,h*.86), Vector2(w,h), Vector2(0,h)]), Color(Design.NIGHT,.30))
