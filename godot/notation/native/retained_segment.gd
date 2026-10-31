extends Node2D
## A single retained CanvasItem command list for authentic native source ink.
## Godot records _draw once per score/viewport/hand revision. The practice view
## subsequently changes position/visibility, never queue_redraw on each beat.
var owner_view
var kind := "source"
var variant := "first"
var note_instances: Array = []
var symbols_drawn := 0
var beam_groups_drawn := 0
var compiled := false

func configure(view: Control, segment_kind: String, segment_variant: String) -> void:
    owner_view = view
    kind = segment_kind
    variant = segment_variant
    compiled = false
    queue_redraw()

func _draw() -> void:
    compiled = false
    note_instances.clear()
    if owner_view == null or not owner_view.native_ready:
        return
    if kind == "source":
        var frame = owner_view.paint_retained_source(self,variant)
        if frame == null:
            return
        note_instances = frame.drawn_note_instances.duplicate(true)
        symbols_drawn = frame.visible_symbols
        beam_groups_drawn = frame.visible_beam_groups
    else:
        owner_view.paint_retained_rest(self)
    compiled = true
    # The parent may already have projected this frame before our first draw.
    # Update notehead hit regions on the next frame, once, without rebuilding ink.
    owner_view.queue_redraw()
