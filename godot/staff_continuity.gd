extends Control

# One visual staff spanning all preloaded engraved systems. Individual systems
# preserve their Verovio noteheads, clefs, accidentals and barlines; this quiet
# background joins the short raster gutters at page/system boundaries.
var staff_lines: Array = []

func _init() -> void:
    mouse_filter = Control.MOUSE_FILTER_IGNORE
    focus_mode = Control.FOCUS_NONE

func set_rails(lines: Array) -> void:
    staff_lines = lines.duplicate()
    queue_redraw()

func _draw() -> void:
    if staff_lines.is_empty() or size.x <= 1.0 or size.y <= 1.0:
        return
    # Match the bright engraved rule color at the safe raster seams.
    # A dimmer underlay leaves visibly chopped staff endpoints.
    var ink := Color("#486558", 0.79)
    for normalized in staff_lines:
        var y: float = float(normalized) * size.y
        if y < 0.0 or y > size.y:
            continue
        draw_line(Vector2(0.0, y), Vector2(size.x, y), ink, 1.15, true)
