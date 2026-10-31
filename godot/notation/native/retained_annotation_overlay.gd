extends Node2D
## Dynamic instructional annotations render above retained source ink.
## The source glyph command buffers are never invalidated by transport ticks.
var owner_view

func _draw() -> void:
    if owner_view != null:
        owner_view.paint_retained_annotations(self)
