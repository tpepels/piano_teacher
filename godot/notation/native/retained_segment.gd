extends Node2D
## A single retained CanvasItem command list for authentic native source ink.
## Godot records _draw once per score/viewport/hand revision. The practice view
## subsequently changes position/visibility, never queue_redraw on each beat.
const NoteStatusLayer := preload("res://notation/native/note_status_layer.gd")
var painter
var _canvas_ref: WeakRef
var _compiled_callback: Callable
var kind := "source"
# A retained source CanvasItem owns one immutable source interval. Its draw
# commands are never the whole piece when only one measure is visible.
var source_floor := -INF
var source_ceiling := INF
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
var compile_enabled := true

func configure(canvas: Control, source_painter, compiled_callback: Callable,
        segment_kind: String) -> void:
    _canvas_ref = weakref(canvas)
    painter = source_painter
    _compiled_callback = compiled_callback
    kind = segment_kind
    compiled = false
    if kind == "source" and status_layer == null:
        status_layer = NoteStatusLayer.new(self)
        add_child(status_layer)
    queue_redraw()

func set_source_window(first: float, last: float) -> void:
    if kind != "source" or not is_finite(first) or \
            not is_finite(last) or first >= last:
        return
    if absf(source_floor-first) < .00001 and \
            absf(source_ceiling-last) < .00001:
        return
    source_floor = first
    source_ceiling = last
    # A differently cropped source window cannot reuse the previous
    # CanvasItem command list. The owner places it offscreen to compile
    # before its actual viewport clip can become visible.
    compiled = false
    queue_redraw()


## Bind the strip's current take and the ledger; repaints only on change.
func sync_note_status(take_key: String, source, visible_ink: bool,
        physical_source_bounds: Vector2 = Vector2(NAN,NAN)) -> void:
    if status_layer != null:
        status_layer.sync(take_key,source,visible_ink,physical_source_bounds)

func _draw() -> void:
    if not compile_enabled:
        return
    var began: int = Time.get_ticks_usec() if OS.get_environment("PIANO_TEACHER_TIMING_DIAGNOSTICS") == "1" else 0
    compiled = false
    note_instances.clear()
    instances_by_event.clear()
    compile_generation += 1
    if painter == null or not painter.native_ready or \
            painter.size.x < 100.0 or painter.size.y < 100.0:
        return
    if kind == "source":
        var frame = painter.paint_retained_source(self)
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
        painter.paint_retained_rest(self)
    compiled = true
    if began > 0 and Time.get_ticks_usec()-began >= 8000:
        print("RETAINED_DRAW_WORK:",JSON.stringify({"at_ms":float(began)*.001,
            "elapsed_ms":float(Time.get_ticks_usec()-began)*.001,
            "kind":kind,"notes":note_instances.size(),"generation":compile_generation}))
    # The parent may already have projected this frame before our first draw.
    # Update notehead hit regions on the next frame, once, without rebuilding ink.
    var canvas = _canvas_ref.get_ref()
    if canvas != null:
        canvas.queue_redraw()
        _compiled_callback.call()
