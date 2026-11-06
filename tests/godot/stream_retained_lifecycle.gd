extends SceneTree
## Real CanvasItem lifecycle: uncompiled source/rest graphics must compile
## without ever appearing at the world origin, then travel, retire and reuse.
const Lifecycle := preload("res://notation/native/stream_lifecycle.gd")
const Segment := preload("res://notation/native/retained_segment.gd")
const RenderPass := preload("res://notation/native/render_pass.gd")

class InkOwner extends Control:
    var native_ready := true
    var source_draws := 0
    var rest_draws := 0
    var compiled_events := 0
    func paint_retained_source(canvas: CanvasItem) -> RefCounted:
        source_draws += 1
        canvas.draw_rect(Rect2(5,5,30,20),Color.WHITE)
        var frame = RenderPass.new()
        frame.drawn_note_instances = [{"event_id":"a","source_id":"a",
            "position":Vector2(30,30),"pass_index":0}]
        return frame
    func paint_retained_rest(canvas: CanvasItem) -> void:
        rest_draws += 1
        canvas.draw_rect(Rect2(5,5,30,20),Color.WHITE)
    func retained_segment_compiled() -> void:
        compiled_events += 1

var failures := 0
func check(ok: bool, message: String) -> void:
    if not ok:
        failures += 1
        printerr("STREAM_LIFECYCLE_FAILED:",message)
func _initialize() -> void:
    call_deferred("_exercise")

func _exercise() -> void:
    var owner := InkOwner.new()
    owner.size = Vector2(800,420)
    root.add_child(owner)
    var note := Segment.new()
    owner.add_child(note)
    note.configure(owner,"source")
    var rest := Segment.new()
    owner.add_child(rest)
    rest.configure(owner,"rest")
    var source_pass: Dictionary = Lifecycle.create(
        owner,note,"source",20.0,0.0,4.0,"active",1,false)
    var rest_pass: Dictionary = Lifecycle.create(
        owner,rest,"rest",24.0,0.0,4.0,"rest",-1,false)
    var passes: Array = [source_pass,rest_pass]
    check(not source_pass["clip"].visible and
        not rest_pass["clip"].visible,
        "newly allocated clips must remain hidden before retained compilation")
    check(note.get_parent() == owner and rest.get_parent() == owner,
        "uncompiled source AND rest must stay attached to visible owner")
    await process_frame
    await process_frame
    RenderingServer.force_draw()
    check(note.compiled and rest.compiled and owner.source_draws > 0 and
        owner.rest_draws > 0,
        "source and semantic rest both compile before entering a hidden clip")
    Lifecycle.attach_compiled(passes)
    check(Lifecycle.project(source_pass,19.0,264.0,90.0,20.0,
        owner.size,4.0),"compiled note can be projected")
    check(Lifecycle.project(rest_pass,19.0,264.0,90.0,20.0,
        owner.size,4.0),"compiled rest can be projected")
    check(note.get_parent() == source_pass["clip"] and
        rest.get_parent() == rest_pass["clip"] and
        source_pass["clip"].visible and rest_pass["clip"].visible,
        "one lifecycle owner attaches and reveals both classes of ink")
    var initial_source_draws := owner.source_draws
    var initial_rest_draws := owner.rest_draws
    # A hand change/resize invalidates BOTH kinds of printed ink. Every
    # retained segment must leave its clip before Godot can compile again.
    Lifecycle.prepare_recompile(owner,passes)
    for segment in [note,rest]:
        segment.compiled = false
        segment.queue_redraw()
    check(note.get_parent() == owner and rest.get_parent() == owner and
        not source_pass["clip"].visible and not rest_pass["clip"].visible,
        "invalidation detaches both segments from hidden clip parents")
    await process_frame
    await process_frame
    RenderingServer.force_draw()
    check(note.compiled and rest.compiled and
        owner.source_draws > initial_source_draws and
        owner.rest_draws > initial_rest_draws,
        "source and rest must both re-engrave after a viewport change")
    Lifecycle.attach_compiled(passes)
    check(Lifecycle.project(source_pass,25.0,264.0,90.0,20.0,
        owner.size,4.0),"recompiled note is reusable")
    check(Lifecycle.project(rest_pass,25.0,264.0,90.0,20.0,
        owner.size,4.0),"recompiled rest is reusable")
    check(not Lifecycle.expired(source_pass,27.0,90.0,264.0,20.0,4.0),
        "trailing printed note ink must be retained until it is fully offscreen")
    var removed: Array[int] = Lifecycle.prune(
        owner,passes,29.0,90.0,264.0,20.0,4.0)
    check(removed == [1] and passes.size()==1 and
        note.get_parent() == owner and not note.visible,
        "expired source returns to the precompiled pool, rest stays present")
    removed = Lifecycle.prune(owner,passes,34.0,90.0,264.0,20.0,4.0)
    check(removed == [-1] and passes.is_empty() and
        rest.get_parent() == owner and not rest.visible,
        "printed semantic rest retires through the same lifecycle")
    var source_reuse: Dictionary = Lifecycle.create(
        owner,note,"source",40.0,0.0,4.0,"retry",2,false)
    var rest_reuse: Dictionary = Lifecycle.create(
        owner,rest,"rest",44.0,0.0,4.0,"rest",-2,false)
    var reused: Array = [source_reuse,rest_reuse]
    check(Lifecycle.project(source_reuse,34.0,264.0,90.0,20.0,
        owner.size,4.0) and Lifecycle.project(rest_reuse,34.0,
        264.0,90.0,20.0,owner.size,4.0),
        "retired retained ink is reusable without recompilation")
    check(owner.source_draws == initial_source_draws+1 and
        owner.rest_draws == initial_rest_draws+1,
        "moving/reusing segments cannot repaint source or rest")
    Lifecycle.release_all(owner,reused)
    check(reused.is_empty() and note.get_parent()==owner and
        rest.get_parent()==owner and not note.visible and not rest.visible,
        "reload releases all source and rest windows and retains cached ink")
    owner.queue_free()
    print("STREAM_LIFECYCLE_FAILURES:",failures)
    quit(0 if failures==0 else 1)
