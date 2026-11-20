extends Node2D
## Dynamic instructional annotations render above retained source ink.
## The source glyph command buffers are never invalidated by transport ticks.
var painter

func _draw() -> void:
    if painter != null:
        painter.paint_retained_annotations(self)
