extends Node2D
## A single retained CanvasItem command list for authentic native source ink.
## Godot records _draw once per score/viewport/hand revision. The practice view
## subsequently changes position/visibility, never queue_redraw on each beat.
const NoteStatusLayer := preload("res://notation/native/note_status_layer.gd")
var owner_view
var kind := "source"
# Immutable engraved heads of this strip in strip-local coordinates, sorted
# by X, each with its paint metadata (head mask, ink, staff space).
var note_instances: Array = []
var instances_by_event: Dictionary = {}
var compile_generation := 0
# Status ink lives INSIDE the strip: same transform, same clip window.
var status_layer
var symbols_drawn := 0
var beam_groups_drawn := 0
var compiled := false

func configure(view: Control, segment_kind: String) -> void:
    owner_view = view
    kind = segment_kind
    compiled = false
    if kind == "source" and status_layer == null:
        status_layer = NoteStatusLayer.new(self)
        add_child(status_layer)
    queue_redraw()

## Bind the strip's current take and the ledger; repaints only on change.
func sync_note_status(take_key: String, source, visible_ink: bool) -> void:
    if status_layer != null:
        status_layer.sync(take_key,source,visible_ink)

func _draw() -> void:
    compiled = false
    note_instances.clear()
    instances_by_event.clear()
    compile_generation += 1
    if owner_view == null or not owner_view.native_ready or \
            owner_view.size.x < 100.0 or owner_view.size.y < 100.0:
        return
    if kind == "source":
        var frame = owner_view.paint_retained_source(self)
        if frame == null:
            return
        note_instances = frame.drawn_note_instances.duplicate(true)
        # Screen projection selects a small contiguous interval by binary
        # search. Do not scan a whole score every 60 Hz frame.
        note_instances.sort_custom(func(a: Dictionary,b: Dictionary) -> bool:
            return a["position"].x < b["position"].x)
        for instance in note_instances:
            var id: String = str(instance["event_id"])
            if not instances_by_event.has(id):
                instances_by_event[id] = []
            instances_by_event[id].append(instance)
        symbols_drawn = frame.visible_symbols
        beam_groups_drawn = frame.visible_beam_groups
    else:
        owner_view.paint_retained_rest(self)
    compiled = true
    # The parent may already have projected this frame before our first draw.
    # Update notehead hit regions on the next frame, once, without rebuilding ink.
    owner_view.queue_redraw()
    owner_view.retained_segment_compiled()
