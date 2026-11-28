extends SceneTree
## Semantic source windows and already-compiled buffers are fixtures, not a
## simulated app. Production admission, binding, queue and projection run here.
const Flow := preload("res://continuous_score_flow.gd")
const Controller := preload("res://notation/native/score_stream_controller.gd")
const Pool := preload("res://notation/native/retained_notation_pool.gd")
const Geometry := preload("res://notation/native/stream_geometry.gd")
const Lifecycle := preload("res://notation/native/stream_lifecycle.gd")
const Admission := preload("res://score_stream_admission.gd")
var failures := 0

func check(ok: bool, message: String) -> void:
    if not ok:
        failures += 1
        printerr("SCORE_STREAM_FAIL: ",message)

func geometry(world: float):
    return Geometry.new(true,world,100.0,20.0,4.0,1000.0,330.0,4.0,2.0)

func facts(controller, world: float) -> Dictionary:
    var result: Dictionary = controller.preflight_facts(world,0.0,true,6.7,0.4,
        100.0,20.0,4.0,1000.0,330.0)
    result.merge({"ready":true,"duration":4.0,"density":100.0,"gap":20.0,
        "width":1000.0,"playhead":330.0,"rest_gap":4.0,"bpm":60.0})
    return result

func acknowledge(controller, world: float, key: String, segment: String) -> void:
    check(controller.bind_segment(segment) and controller.acknowledge_arm(),"The authorized take can be acknowledged")
    controller.observe_transport(geometry(world),world,0.0,0.0,key,"count_in",false,true,true,segment,true)

func fixed_music(snapshot: Array) -> Array:
    var result: Array = []
    for item in snapshot:
        result.append([item.world_origin,item.source_floor,item.source_ceiling,item.kind])
    return result

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var canvas := Control.new()
    root.add_child(canvas)
    var pool := Pool.new()
    var controller := Controller.new()
    var windows: Array[Vector2] = [Vector2(0.0,4.0)]
    pool.install(canvas,windows)
    for segment in pool.repeat_segments:
        check(segment.source_floor == 0.0 and segment.source_ceiling == 4.0,
            "Single-measure repeat buffers are seeded with the exact source window")
    controller.bind_surface(canvas,pool,func(_opening: float) -> Array[Vector2]: return windows)
    # The musical timeline put the first note one count-in bar ahead.
    var armed: Dictionary = controller.place_timeline_take(geometry(0.0),0.0,4.0,6.7,0.4,4.0)
    check(not armed.is_empty() and absf(float(armed.get("start_world",0.0))-4.0) < .0001,
        "A take is drawn exactly at its timeline world start")
    acknowledge(controller,0.0,"piece|7|10|practice","first")
    var original: Array = controller.online_snapshot()
    var music: Array = fixed_music(original)
    # Admit a second, unseen preparation; Pause must preserve exposed music.
    for item in controller.queue.online:
        item.segment.compiled = true
    controller.attach_compiled()
    for item in controller.queue.online:
        Lifecycle.project(item,5.0,330.0,100.0,20.0,Vector2(1000,600),4.0)
    # The live take has sounded: the playhead passed its first note.
    controller.queue.mark_sounded(int(controller.queue.online[0].get("take_owner",
        controller.queue.online[0]["serial"])),5.0)
    var first: Dictionary = controller.queue.online[0]
    check(bool(first.get("ever_visible",false)),"The admitted source reaches the visible score")
    var before_x: float = first.clip.position.x+first.segment.position.x
    controller.observe_transport(geometry(5.0),5.0,0.0,0.0,"piece|7|10|practice","paused",true,false,true,"first",true)
    controller.observe_transport(geometry(5.5),5.5,0.0,0.0,"piece|7|10|practice","paused",true,false,true,"first",true)
    check(fixed_music(controller.online_snapshot()) == music,"Pause preserves every committed source and release boundary")
    Lifecycle.project(first,5.5,330.0,100.0,20.0,Vector2(1000,600),4.0)
    # This is a raw geometric projection at a later supplied world beat.
    # The owning presentation session freezes that input beat on Pause.
    check(first.clip.position.x+first.segment.position.x < before_x,
        "Source projects forward for increasing world time without moving its binding")
    # Resume while playing continues after the ink still ahead, plus a bar.
    var ahead: float = controller.ink_end(geometry(5.5))
    check(is_finite(ahead) and ahead >= 8.0,
        "The printed ink still ahead of the playhead is reported to Python")
    var resumed: Dictionary = controller.place_timeline_take(geometry(5.5),0.0,
        ahead+4.0,6.7,0.4,4.0)
    check(not resumed.is_empty(),"Resume draws the continuation where the timeline put it")
    acknowledge(controller,5.5,"piece|7|10|practice","resume")
    var after_resume: Array = controller.online_snapshot()
    check(fixed_music(after_resume).slice(0,1) == music.slice(0,1),
        "Resume preserves the original paused source while replacing its invisible rest")
    check(controller.visible_take_keys().has("piece|7|10|practice"),"Resume retains the attempt's performance identity")
    # Retry draws a new copy after the ink ahead; it never re-anchors the old one.
    var restarted: Dictionary = controller.place_timeline_take(geometry(6.0),0.0,
        controller.ink_end(geometry(6.0))+4.0,6.7,0.4,4.0)
    check(not restarted.is_empty(),"Retry draws its new take")
    acknowledge(controller,6.0,"piece|7|11|practice","retry")
    check(fixed_music(controller.online_snapshot()).slice(0,1) == music.slice(0,1),
        "Retry preserves the original exposed source without relocating it")
    check(controller.visible_take_keys().has("piece|7|10|practice")
        and controller.visible_take_keys().has("piece|7|11|practice"),"Old and retried score copies keep separate results")
    # A recovery can authorize another segment without changing the
    # transport key. It must bind the exact new arm, not the old source.
    var recovery: Dictionary = controller.place_timeline_take(geometry(6.0),0.0,
        controller.ink_end(geometry(6.0))+4.0,6.7,0.4,4.0)
    check(not recovery.is_empty(),"Same-transport recovery draws its new segment")
    acknowledge(controller,6.0,"piece|7|11|practice","recovery")
    check(controller.bound_segment() == "recovery",
        "A new acknowledged segment binds even when transport identity is unchanged")
    controller.observe_transport(geometry(6.0),6.0,0.0,0.0,"piece|7|11|practice","count_in",false,true,true,"unreceived",true)
    check(controller.bound_segment().is_empty(),
        "An old same-transport owner cannot attest a different segment")
    # A real one-bar printed rest must reserve the following native header
    # *inside* that bar's musical silence, otherwise a fixed four-beat repeat
    # becomes impossible even when no source notes overlap. Use this same
    # current controller, queue and physical admission path.
    var automatic_controller := Controller.new()
    var automatic_pool := Pool.new()
    var automatic_canvas := Control.new()
    root.add_child(automatic_canvas)
    automatic_pool.install(automatic_canvas,windows)
    automatic_controller.bind_surface(automatic_canvas,automatic_pool,
        func(_beat: float) -> Array[Vector2]: return windows)
    automatic_controller.append_source(geometry(0.0),0.0,4.0,0.0,"prepared",true)
    var rest_snapshot: Array = automatic_controller.online_snapshot()
    var authored_rest: Dictionary = rest_snapshot[-1]
    check(str(authored_rest.get("kind","")) == "rest" and
        float(authored_rest.get("source_ceiling",INF)) < 4.0,
        "Count-in rest reserves physical header space without changing the musical bar")
    # Source sounds from world 4 through 8. Its one-bar count-in rest
    # occupies [8,12); the repeat's first note is at 12.
    automatic_controller.queue.mark_sounded(int(automatic_controller.queue.online[0].get(
        "take_owner",automatic_controller.queue.online[0]["serial"])),9.0)
    var next_armed: Dictionary = automatic_controller.place_timeline_take(
        geometry(9.0),0.0,12.0,6.7,0.4,4.0)
    check(not next_armed.is_empty(),
        "A one-bar repeat after the written rest is drawn at its timeline place")
    for item in automatic_controller.queue.online:
        automatic_controller.queue.mark_sounded(int(item.get("take_owner",item["serial"])),13.0)
    var overlapping: Dictionary = automatic_controller.place_timeline_take(
        geometry(13.0),0.0,14.0,6.7,0.4,4.0)
    check(overlapping.is_empty(),"A take may never overlap ink already drawn")
    automatic_canvas.free()

    # A visible unplayed source survives Resume/Retry; the new copy must
    # follow the physically retained ink. A forecast never publishes notes.
    var abandon_controller := Controller.new()
    var abandon_pool := Pool.new()
    var abandon_canvas := Control.new()
    root.add_child(abandon_canvas)
    abandon_pool.install(abandon_canvas,windows)
    abandon_controller.bind_surface(abandon_canvas,abandon_pool,
        func(_beat: float) -> Array[Vector2]: return windows)
    check(not abandon_controller.place_timeline_take(geometry(0.0),0.0,4.0,6.7,0.4,4.0).is_empty(),
        "The first exposure is drawn")
    acknowledge(abandon_controller,0.0,"piece|7|10|practice","original")
    var retained: Array = fixed_music(abandon_controller.online_snapshot())
    var old_owner: int = int(abandon_controller.queue.online[0]["take_owner"])
    for item in abandon_controller.queue.online:
        item["ever_visible"] = true
    var clearance: float = abandon_controller.ink_end(geometry(0.5))
    check(is_finite(clearance) and clearance >= 8.0,
        "Visible unplayed ink remains in the physical clearance calculation")
    abandon_controller.withdraw_predicted_take(geometry(0.5),old_owner)
    check(fixed_music(abandon_controller.online_snapshot()) == retained,
        "Cancellation cannot retract previously visible notation")
    check(abandon_controller.place_predicted_take(geometry(0.5),0.0,clearance+4.0) < 0
        and fixed_music(abandon_controller.online_snapshot()) == retained,
        "An uncommitted prediction cannot publish source ink")
    check(not abandon_controller.place_timeline_take(geometry(0.5),0.0,clearance+4.0,6.7,0.4,4.0).is_empty()
        and fixed_music(abandon_controller.online_snapshot()).slice(0,retained.size()) == retained,
        "The committed successor follows the visible abandoned take")
    abandon_canvas.free()

    # An already printed leading count-in rest does not force an unseen
    # abandoned measure and its following rest to scroll through at 22 BPM.
    var slow := Controller.new()
    var slow_pool := Pool.new()
    var slow_canvas := Control.new()
    root.add_child(slow_canvas)
    slow_pool.install(slow_canvas,windows)
    slow.bind_surface(slow_canvas,slow_pool,
        func(_beat: float) -> Array[Vector2]: return windows)
    check(not slow.place_timeline_take(geometry(0.0),0.0,10.0,6.7,0.4,4.0).is_empty(),
        "Slow transport admits a count-in and future source")
    acknowledge(slow,0.0,"piece|7|10|practice","slow")
    var leading: Dictionary = slow.queue.online[0]
    check(str(leading.get("rest_position","")) == "before",
        "Fixture includes a leading count-in rest")
    leading["ever_visible"] = true
    var before_clearance: float = float(leading["world_origin"])+float(leading["source_ceiling"])
    check(absf(slow.ink_end(geometry(0.0))-before_clearance) < .0001,
        "Timed clearance excludes the still-unseen source behind a printed rest")
    var preserved_slot: String = str(leading["slot_id"])
    check(not slow.place_timeline_take(geometry(0.0),0.0,before_clearance+4.0,6.7,0.4,4.0).is_empty(),
        "Retry is placed after the preserved rest rather than an unseen abandoned passage")
    check(str(slow.queue.online[0]["slot_id"]) == preserved_slot and
        bool(slow.queue.online[0].get("detached_leading_rest",false)),
        "The original rest stays at its immutable world position")
    check(not slow.queue.has_take(1),"Detached rest cannot attest an old graded take")
    var original_archives := 0
    for entry in slow.offline_snapshot():
        if int(entry.get("owner_serial",-1)) == 1:
            original_archives += 1
    check(original_archives == 1,"The withdrawn source is archived once")
    check(slow.reset(),"Reset journals the replacement but not the detached rest twice")
    var original_after_reset := 0
    for entry in slow.offline_snapshot():
        if int(entry.get("owner_serial",-1)) == 1:
            original_after_reset += 1
    check(original_after_reset == original_archives,
        "Detached rest reset cannot duplicate the already archived original source")
    slow_canvas.free()

    # Resume must not drag an unseen trailing rest behind already printed
    # source ink before adding ANOTHER complete count-in.
    var trim_canvas := Control.new()
    root.add_child(trim_canvas)
    var trim_pool := Pool.new()
    var trim_controller := Controller.new()
    trim_pool.install(trim_canvas,windows)
    trim_controller.bind_surface(trim_canvas,trim_pool,
        func(_beat: float) -> Array[Vector2]: return windows)
    check(not trim_controller.place_timeline_take(geometry(0.0),0.0,10.0,6.7,0.4,4.0).is_empty(),
        "Trailing-rest fixture is admitted")
    acknowledge(trim_controller,0.0,"piece|7|10|practice","trim")
    var trim_queue = trim_controller.queue
    var source: Dictionary = trim_queue.online[-2]
    var rest: Dictionary = trim_queue.online[-1]
    source["ever_visible"] = true
    var source_slot: String = str(source["slot_id"])
    var preview: Array = trim_queue.preview_timed_withdrawal(0.0,100.0,10.0,4.0,670.0,200.0)
    check(preview.size() == trim_queue.online.size()-1 and str(preview[-1]["slot_id"]) == source_slot,
        "Preview drops only unseen trailing silence")
    var removed: Array[int] = trim_queue.withdraw_timed_tail(trim_canvas,0.0,100.0,10.0,4.0,670.0,200.0,"resume")
    check(removed.size() == 1 and str(trim_queue.online[-1]["slot_id"]) == source_slot,
        "Withdrawal matches preview and keeps the source identity")
    check(trim_queue.has_take(int(source["take_owner"])), "Rest removal cannot discard its source take")
    check(trim_queue.offline.is_empty(),"Unseen silence is not a separate recoverable source")
    trim_canvas.free()

    # Free (owner report 2026-11-25): Python holds the staff at the target
    # it schedules from the view's reported travel distance; the passage
    # must be drawn exactly there, on an empty staff and after a take.
    for with_take in [false, true]:
        var free_controller := Controller.new()
        var free_pool := Pool.new()
        var free_canvas := Control.new()
        root.add_child(free_canvas)
        free_pool.install(free_canvas,windows)
        free_controller.bind_surface(free_canvas,free_pool,
            func(_beat: float) -> Array[Vector2]: return windows)
        var world := 0.0
        if with_take:
            free_controller.place_timeline_take(geometry(0.0),0.0,4.0,6.7,0.4,4.0)
            acknowledge(free_controller,0.0,"piece|7|10|practice","take")
            world = 0.5   # its notes are still ahead on the staff
        var travel: float = free_controller.free_opening(geometry(world),6.7,0.4)-world+.25
        var target: float = world+maxf(4.0,travel)
        if not with_take:
            check(target-world == 4.0,"Empty Free strip uses one bar, not viewport width")
        else:
            check(target-world >= 4.0,"Free keeps clearance from prior retained ink")
        var placed: bool = free_controller.schedule_recovery(geometry(world),world,0.0,
            target,6.7,0.4,"free:%s" % str(with_take),false,0.0,false,true)
        check(placed and absf(free_controller.scheduled_plan_opening(
            "free:%s" % str(with_take))-target) < .0001,
            "A Free target is drawn exactly where Python holds the staff (after a take: %s)" % \
                str(with_take))
        free_canvas.free()
    var flow := Flow.new()
    flow.backend_clock = func(): return float(Time.get_ticks_msec())
    var t0: float = float(Time.get_ticks_msec())
    flow.follow({"run":1,"end_world":null,"holds_ms":[],"next_take":null,"segments":[
        {"kind":"rest","world_start":0.0,"start_ms":t0,"beats":8.0,
            "spans":[[8.0,60.0,60.0]],"hold_ms":null}]},int(t0))
    flow.sample(int(t0)+1000)
    var previous: float = flow.sample(int(t0)+2000)
    check(flow.sample(int(t0)+3000) > previous and flow.sample(int(t0)+2500) >= previous,
        "Delayed frames cannot rewind the score world")
    canvas.free()
    print("SCORE_STREAM_FAILURES:",failures)
    quit(0 if failures == 0 else 1)
