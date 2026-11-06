extends SceneTree
## One retained-score lifecycle, shared by source notes, semantic rests,
## fast retries and score reloads. Real CanvasItems verify compiled ink.
const Lifecycle := preload("res://notation/native/stream_lifecycle.gd")
const Segment := preload("res://notation/native/retained_segment.gd")
const RenderPass := preload("res://notation/native/render_pass.gd")

class InkOwner extends Control:
    var native_ready := true
    var source_draws := 0
    var rest_draws := 0
    var compiled_events := 0
    func _new_retained_segment(kind: String):
        var part := Segment.new()
        add_child(part)
        part.configure(self,kind)
        return part
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

func specs(serial: int, first: float, key: String,
        hidden: bool = false) -> Array:
    return [
        {"kind":"source","owner_serial":serial,"world_origin":first,
            "source_floor":0.0,"source_ceiling":4.0,
            "take_key":key,"pending":hidden,
            "hidden_until_armed":hidden},
        {"kind":"rest","owner_serial":serial,"world_origin":first+4.0,
            "source_floor":0.0,"source_ceiling":4.0,"take_key":"rest",
            "pending":false,"hidden_until_armed":hidden}
    ]

func _exercise() -> void:
    var owner := InkOwner.new()
    owner.size = Vector2(800,420)
    root.add_child(owner)
    var note = owner._new_retained_segment("source")
    var rest = owner._new_retained_segment("rest")
    var source_pool: Array = []
    var rest_pool: Array = [rest]
    var passes: Array = []
    var initial: Array = specs(1,20.0,"prepared",true)
    check(Lifecycle.admit(owner,passes,initial,
        source_pool,rest_pool,note) and passes.size() == 2,
        "one admission creates exactly one source and its paired rest")
    var source_pass: Dictionary = passes[0]
    var rest_pass: Dictionary = passes[1]
    check(source_pass["slot_id"] == "1:source" and
        rest_pass["slot_id"] == "1:rest" and
        source_pass["segment"] == note and rest_pass["segment"] == rest,
        "both content roles share one unique owner ID and their retained pool")
    check(not Lifecycle.admit(owner,passes,initial,
        source_pool,rest_pool,note) and passes.size() == 2,
        "repeating the same owner admission cannot add a duplicate clip")
    check(not source_pass["clip"].visible and
        not rest_pass["clip"].visible and
        note.get_parent() == owner and rest.get_parent() == owner,
        "uncompiled source and rest remain offscreen with hidden windows")
    await process_frame
    await process_frame
    RenderingServer.force_draw()
    check(note.compiled and rest.compiled and
        owner.source_draws == 1 and owner.rest_draws == 1,
        "both content roles compile before a clipping window is visible")
    Lifecycle.attach_compiled(passes)
    check(not Lifecycle.project(source_pass,19.0,264.0,90.0,20.0,
        owner.size,4.0) and not Lifecycle.project(rest_pass,
        19.0,264.0,90.0,20.0,owner.size,4.0),
        "READY must hide BOTH original noteheads and semantic rests")
    check(Lifecycle.reposition(passes,1,21.0) and
        float(source_pass["world_origin"]) == 21.0 and
        float(rest_pass["world_origin"]) == 25.0,
        "retiming an unplayed source moves its paired rest exactly once")
    check(not Lifecycle.reposition(passes,1,20.0),
        "unpublished reservation cannot jump backwards")
    check(Lifecycle.activate(passes,1,"piece|1|1|practice",true) and
        not Lifecycle.reposition(passes,1,22.0),
        "armed source/rest cannot change world positions")
    check(Lifecycle.project(source_pass,19.0,264.0,90.0,20.0,
        owner.size,4.0) and Lifecycle.project(rest_pass,19.0,264.0,
        90.0,20.0,owner.size,4.0),
        "Play reveals already-compiled source and rest without re-engraving")
    check(note.get_parent() == source_pass["clip"] and
        rest.get_parent() == rest_pass["clip"] and
        source_pass["clip"].visible and rest_pass["clip"].visible,
        "one lifecycle attaches both clip roles")
    check(Lifecycle.activate(passes,1,"piece|1|1|practice",false),
        "transport acknowledgement binds the same owner without new ink")
    var draws_source: int = owner.source_draws
    var draws_rest: int = owner.rest_draws
    Lifecycle.prepare_recompile(owner,passes)
    for segment in [note,rest]:
        segment.compiled = false
        segment.queue_redraw()
    check(note.get_parent() == owner and rest.get_parent() == owner and
        not source_pass["clip"].visible and not rest_pass["clip"].visible,
        "invalidation unclips both content roles before redraw")
    await process_frame
    await process_frame
    RenderingServer.force_draw()
    check(note.compiled and rest.compiled and
        owner.source_draws == draws_source+1 and
        owner.rest_draws == draws_rest+1,
        "both kinds of ink recompile after a real viewport change")
    Lifecycle.attach_compiled(passes)
    check(Lifecycle.project(source_pass,25.0,264.0,90.0,20.0,
        owner.size,4.0) and Lifecycle.project(rest_pass,25.0,264.0,
        90.0,20.0,owner.size,4.0),
        "recompiled source and rest project from their original owner")
    check(not Lifecycle.expired(source_pass,27.0,90.0,264.0,20.0,4.0),
        "source is not removed before its final engraved pixels leave")
    var removed: Array[int] = Lifecycle.prune(
        owner,passes,30.0,90.0,264.0,20.0,4.0)
    check(removed == [1] and passes.size()==1 and
        note.get_parent() == owner and not note.visible,
        "source retires into its pool while its printed rest remains")
    removed = Lifecycle.prune(owner,passes,35.0,90.0,264.0,20.0,4.0)
    check(removed == [-1] and passes.is_empty() and
        rest.get_parent() == owner and not rest.visible,
        "rest expires using the same world-axis retirement boundary")
    var repeated: Array = specs(2,40.0,"retry")
    check(Lifecycle.admit(owner,passes,repeated,
        source_pool,rest_pool,note) and passes.size()==2,
        "Retry admits a different owner and a single paired rest")
    check(passes[0]["segment"] == note and passes[1]["segment"] == rest,
        "retired source and rest buffers are reused, not re-created")
    check(Lifecycle.activate(passes,2,"piece|1|2|practice",false),
        "retry owner binds exactly one backend transport identity")
    check(Lifecycle.project(passes[0],34.0,264.0,90.0,20.0,
        owner.size,4.0) and Lifecycle.project(passes[1],
        34.0,264.0,90.0,20.0,owner.size,4.0),
        "reused ink scrolls normally")
    check(owner.source_draws == draws_source+1 and
        owner.rest_draws == draws_rest+1,
        "reusing printed ink cannot re-engrave source or rest")
    check(not Lifecycle.admit(owner,passes,repeated,
        source_pool,rest_pool,note) and passes.size()==2,
        "Retry may not install the same passage twice")
    var third: Array = specs(3,55.0,"prepared",true)
    check(Lifecycle.admit(owner,passes,third,
        source_pool,rest_pool,note) and passes.size()==4,
        "another unique future owner uses the same general path")
    check(not Lifecycle.activate(passes,3,"piece|1|2|practice",false),
        "same transport ID and source opening cannot create duplicate notation")
    check(Lifecycle.widen_source(passes,3,2.0,4.0) and
        Lifecycle.activate(passes,3,"piece|1|2|practice",false),
        "Resume may reuse a transport ID with a distinct later source interval")
    var orphan: Array = [specs(4,70.0,"prepared",true)[1]]
    check(not Lifecycle.admit(owner,passes,orphan,
        source_pool,rest_pool,note) and passes.size()==4,
        "a written rest may not be inserted without its source owner")
    var mixed: Array = [specs(4,70.0,"prepared",true)[0],
        specs(5,74.0,"prepared",true)[1]]
    check(not Lifecycle.admit(owner,passes,mixed,
        source_pool,rest_pool,note) and passes.size()==4,
        "one admission cannot combine notes and rests from different takes")
    var misplaced: Array = specs(4,70.0,"prepared",true)
    misplaced[1]["world_origin"] = 71.0
    check(not Lifecycle.admit(owner,passes,misplaced,
        source_pool,rest_pool,note) and passes.size()==4,
        "a rest may never select an independent source-relative placement")
    var nonfinite: Array = specs(4,70.0,"prepared",true)
    nonfinite[0]["world_origin"] = NAN
    check(not Lifecycle.admit(owner,passes,nonfinite,
        source_pool,rest_pool,note) and passes.size()==4,
        "malformed source coordinates cannot create orphan retained graphics")
    var invalid: Array = specs(4,70.0,"prepared",true)
    check(Lifecycle.admit(owner,passes,invalid,
        source_pool,rest_pool,note) and passes.size()==6,
        "a complete later passage is admitted atomically")
    var damaged: Dictionary = passes[4]
    var damaged_rest: Dictionary = passes[5]
    damaged["segment"].free()
    var dropped: Array[int] = Lifecycle.prune(
        owner,passes,34.0,90.0,264.0,20.0,4.0)
    check(dropped.has(4) and dropped.has(-4) and passes.size()==4 and
        damaged_rest["segment"].get_parent() == owner,
        "an invalid source must retire its dependent rest, never orphan it")
    Lifecycle.release_all(owner,passes)
    check(passes.is_empty() and note.get_parent()==owner and
        rest.get_parent()==owner and not note.visible and not rest.visible,
        "score reload releases every source and rest through one path")
    owner.queue_free()
    print("STREAM_LIFECYCLE_FAILURES:",failures)
    quit(0 if failures==0 else 1)
