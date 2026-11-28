extends RefCounted
## Sole owner of retained source/rest CanvasItem allocation, compilation,
## reuse and release for one native score revision. Never chooses a musical
## deadline or mutates the immutable ScoreStreamController queue.
const RetainedSegment := preload("res://notation/native/retained_segment.gd")
const RetainedAnnotationOverlay := preload("res://notation/native/retained_annotation_overlay.gd")
const StreamLifecycle := preload("res://notation/native/stream_lifecycle.gd")

var _canvas_ref: WeakRef
var _painter
var _compiled_callback: Callable

func bind_painter(painter, compiled_callback: Callable) -> void:
    _painter = painter
    _compiled_callback = compiled_callback

func allocate(kind: String):
    return _new_segment(_canvas_ref.get_ref(),kind)

var first_once
var repeat_segments: Array = []
var rest_segments: Array = []
var all_segments: Array = []
var annotations: Node2D
var generation := 0
var _initial_compilation: Array = []

func _invalidate_publication() -> void:
    generation += 1

func clear(view: Control) -> void:
    _invalidate_publication()
    _initial_compilation.clear()
    for segment in [first_once,annotations] + \
            repeat_segments + rest_segments:
        if segment != null and is_instance_valid(segment):
            if segment.get_parent() == view:
                view.remove_child(segment)
            segment.queue_free()
    first_once = null
    annotations = null
    repeat_segments.clear()
    rest_segments.clear()
    all_segments.clear()

func _new_segment(view: Control, kind: String):
    _invalidate_publication()
    _canvas_ref = weakref(view)
    var segment = RetainedSegment.new()
    view.add_child(segment)
    all_segments.append(segment)
    segment.configure(view,_painter,_compiled_callback,kind)
    return segment

func install(view: Control, windows: Array[Vector2], incremental: bool = false) -> void:
    # The view already released the old stream ledger before calling this.
    clear(view)
    view.clip_contents = true
    first_once = _new_segment(view,"source")
    resize(view,windows,true)
    annotations = RetainedAnnotationOverlay.new()
    annotations.set("painter",_painter)
    annotations.z_index = 5
    view.add_child(annotations)
    if incremental:
        _initial_compilation = all_segments.duplicate()
        for segment in _initial_compilation:
            segment.compile_enabled = false
    StreamLifecycle.present_pool(all_segments)

func advance_initial_compilation() -> void:
    # Enable one initial strip per frame, only after the preceding draw.
    while not _initial_compilation.is_empty():
        var segment = _initial_compilation[0]
        if not is_instance_valid(segment) or segment.compiled:
            _initial_compilation.pop_front()
            continue
        if not segment.compile_enabled:
            segment.compile_enabled = true
            segment.visible = true
            segment.queue_redraw()
        return

func resize(view: Control, windows: Array[Vector2], reseed: bool = false) -> void:
    if first_once == null:
        return
    # Pre-engrave one authentic source interval per measure, then retain
    # additional source and silent rest strips for future immutable takes.
    # Only an unbound pool may be reseeded. Admission owns every bound
    # segment's context/Resume crop, regardless of its pool-array position.
    if reseed and not windows.is_empty():
        if first_once.source_floor != windows[0].x or first_once.source_ceiling != windows[0].y:
            _invalidate_publication()
        first_once.set_source_window(windows[0].x,windows[0].y)
    var required: int = maxi(4,windows.size()-1)
    while repeat_segments.size() < required:
        var index: int = repeat_segments.size()+1
        var segment = _new_segment(view,"source")
        if not windows.is_empty():
            var bounds: Vector2 = windows[index % windows.size()]
            segment.set_source_window(bounds.x,bounds.y)
        repeat_segments.append(segment)
    if reseed and not windows.is_empty():
        # Spare buffers should contain actual source windows too. A
        # one-measure lesson needs several precompiled copies of the same
        # measure, not four unused whole-atlas command lists.
        for index in range(repeat_segments.size()):
            var bounds: Vector2 = windows[(index+1) % windows.size()]
            var segment = repeat_segments[index]
            if segment.source_floor != bounds.x or segment.source_ceiling != bounds.y:
                _invalidate_publication()
            segment.set_source_window(bounds.x,bounds.y)
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

func record_compilation(ready_now: bool) -> bool:
    # A transport binding can crop and recompile an existing source strip
    # without reallocating this pool. Every completed command buffer changes
    # the published generation, including such admission-time recompiles.
    generation += 1
    return ready_now

func attach_compiled(online: Array) -> void:
    # Source and semantic rest CanvasItems belong to the same retained
    # resource lifetime. Never reparent from the renderer's draw callback.
    StreamLifecycle.attach_compiled(online)


func invalidate(view: Control, online: Array) -> void:
    _invalidate_publication()
    # Unstage before recompilation: Godot cannot rebuild draw commands
    # beneath an invisible clipping parent.
    StreamLifecycle.prepare_recompile(view,online)
    var initial_pending: bool = not _initial_compilation.is_empty()
    if initial_pending:
        _initial_compilation.clear()
    for segment in [first_once] + repeat_segments + rest_segments:
        if segment != null and is_instance_valid(segment):
            segment.compiled = false
            if initial_pending:
                segment.compile_enabled = false
                _initial_compilation.append(segment)
            segment.queue_redraw()
    StreamLifecycle.present_pool(all_segments)
