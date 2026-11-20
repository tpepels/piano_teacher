extends RefCounted
## Sole owner of retained source/rest CanvasItem allocation, compilation,
## reuse and release for one native score revision. Never chooses a musical
## deadline or mutates the immutable ScoreStreamController queue.
const RetainedSegment := preload("res://notation/native/retained_segment.gd")
const RetainedAnnotationOverlay := preload("res://notation/native/retained_annotation_overlay.gd")
const StreamLifecycle := preload("res://notation/native/stream_lifecycle.gd")

var first_once
var repeat_segments: Array = []
var rest_segments: Array = []
var all_segments: Array = []
var annotations: Node2D
var ink_published := false

func clear(view: Control) -> void:
    for segment in [first_once,annotations] + \
            repeat_segments + rest_segments:
        if segment != null and is_instance_valid(segment):
            if segment.get_parent() == view:
                view.remove_child(segment)
            segment.queue_free()
    first_once = null
    annotations = null
    ink_published = false
    repeat_segments.clear()
    rest_segments.clear()
    all_segments.clear()

func _new_segment(view: Control, kind: String):
    var segment = RetainedSegment.new()
    view.add_child(segment)
    all_segments.append(segment)
    segment.configure(view,kind)
    return segment

func install(view: Control, windows: Array[Vector2]) -> void:
    # The view already released the old stream ledger before calling this.
    clear(view)
    view.clip_contents = true
    first_once = _new_segment(view,"source")
    resize(view,windows)
    annotations = RetainedAnnotationOverlay.new()
    annotations.set("owner_view",view)
    annotations.z_index = 5
    view.add_child(annotations)
    StreamLifecycle.present_pool(all_segments)

func resize(view: Control, windows: Array[Vector2]) -> void:
    if first_once == null:
        return
    # Pre-engrave one authentic source interval per measure, then retain
    # additional source and silent rest strips for future immutable takes.
    if not windows.is_empty():
        first_once.set_source_window(windows[0].x,windows[0].y)
    var required: int = maxi(4,windows.size()-1)
    while repeat_segments.size() < required:
        repeat_segments.append(_new_segment(view,"source"))
    for index in range(1,windows.size()):
        repeat_segments[index-1].set_source_window(
            windows[index].x,windows[index].y)
    while rest_segments.size() < 5:
        rest_segments.append(_new_segment(view,"rest"))

func ready(native_ready: bool, viewport: Vector2) -> bool:
    if not native_ready or viewport.x < 100.0 or viewport.y < 100.0 or \
            first_once == null or annotations == null:
        return false
    if not first_once.compiled:
        return false
    for segment in repeat_segments + rest_segments:
        if not segment.compiled:
            return false
    return true

func mark_published(ready_now: bool) -> bool:
    if not ready_now or ink_published:
        return false
    ink_published = true
    return true

func attach_compiled(online: Array) -> void:
    # Source and semantic rest CanvasItems belong to the same retained
    # resource lifetime. Never reparent from the renderer's draw callback.
    StreamLifecycle.attach_compiled(online)


func invalidate(view: Control, online: Array) -> void:
    ink_published = false
    # Unstage before recompilation: Godot cannot rebuild draw commands
    # beneath an invisible clipping parent.
    StreamLifecycle.prepare_recompile(view,online)
    for segment in [first_once] + repeat_segments + rest_segments:
        if segment != null and is_instance_valid(segment):
            segment.compiled = false
            segment.queue_redraw()
    StreamLifecycle.present_pool(all_segments)
