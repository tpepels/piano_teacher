extends SceneTree
const Segment := preload("res://notation/native/retained_segment.gd")
const RenderPass := preload("res://notation/native/render_pass.gd")

class FakeView extends Control:
    signal retained_ink_compiled
    var native_ready := true
    var allow_publication := false
    func retained_ready() -> bool:
        return allow_publication
    var source_draws := 0
    var rest_draws := 0
    var finished := 0

    func paint_retained_source(canvas: CanvasItem, _variant: String,
            _context: Dictionary = {}) -> RefCounted:
        source_draws += 1
        canvas.draw_rect(Rect2(10,10,20,12),Color.WHITE)
        var frame = load("res://notation/native/render_pass.gd").new()
        frame.drawn_note_instances = [{"event_id":"n1","source_id":"n1",
            "position":Vector2(20,16),"pass_index":0,"instance_id":"0:n1"}]
        frame.visible_symbols = 1
        return frame

    func paint_retained_rest(canvas: CanvasItem, _context: Dictionary = {}) -> void:
        rest_draws += 1
        canvas.draw_rect(Rect2(10,10,20,12),Color.WHITE)

    func retained_segment_compiled() -> void:
        finished += 1


func _initialize() -> void:
    call_deferred("_exercise")

func _exercise() -> void:
    var failures := 0
    var view := FakeView.new()
    view.size = Vector2(800,400)
    root.add_child(view)
    var source := Segment.new()
    view.add_child(source)
    source.configure(view,"source","once")
    var rest := Segment.new()
    view.add_child(rest)
    rest.configure(view,"rest","normal")
    await process_frame
    await process_frame
    if not source.compiled or not rest.compiled or \
            view.source_draws!=1 or view.rest_draws!=1:
        failures += 1
    if source.note_instances.size()!=1 or \
            source.note_instances[0]["position"]!=Vector2(20,16):
        failures += 1
    source.position = Vector2(-127,0)
    rest.position = Vector2(183,0)
    await process_frame
    await process_frame
    if view.source_draws!=1 or view.rest_draws!=1:
        failures += 1
    source.queue_redraw()
    await process_frame
    await process_frame
    if view.source_draws!=2 or view.rest_draws!=1:
        failures += 1
    # The score service cannot publish a loaded revision before the
    # renderer confirms its retained source/silence buffers are recorded.
    var service = load("res://score_asset_session.gd").new(view)
    service.revision = 3
    service.layout_revision = 3
    service.timeline_model_revision = 3
    service._loaded = true
    service.finish_native_score()
    if service.rendered_revision == 3:
        failures += 1
    view.allow_publication = true
    view.retained_ink_compiled.emit()
    if service.rendered_revision != 3 or not service.is_ready():
        failures += 1
    view.free()
    print("RETAINED_SEGMENT_FAILURES:",failures)
    quit(0 if failures==0 else 1)
