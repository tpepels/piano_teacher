extends SceneTree
## Semantic source windows and already-compiled buffers are fixtures, not a
## simulated app. Production admission, binding, queue and projection run here.
const Flow := preload("res://continuous_score_flow.gd")
const Controller := preload("res://notation/native/score_stream_controller.gd")
const Pool := preload("res://notation/native/retained_notation_pool.gd")
const Geometry := preload("res://notation/native/stream_geometry.gd")
const Lifecycle := preload("res://notation/native/stream_lifecycle.gd")
const Reservation := preload("res://score_transport_reservation.gd")
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
    controller.bind_surface(canvas,pool,func(_opening: float) -> Array[Vector2]: return windows)
    var plan: Dictionary = Reservation.plan_facts(facts(controller,0.0),"start",0.0,0.0,4.0)
    check(bool(plan.get("ok",false)) and float(plan.start_world) >= 4.0,"Play reserves a complete count-in before the first note")
    # A preliminary prepared READY source may have been placed before
    # the backend computes its final, later musical deadline. Only an
    # unexposed prepared strip may be replaced; no authorized/paused
    # source may be repositioned. The pure preflight uses actual queue
    # snapshots, with no second teaching or transport implementation.
    var prepared: Dictionary = {
        "kind":"source", "world_origin":12.0,"source_floor":0.0,
        "source_ceiling":4.0,"pending":true,"armed":false,
        "take_key":"prepared","serial":42,"take_owner":42}
    var prepared_facts: Dictionary = facts(controller,0.0)
    prepared_facts["online"] = [prepared]
    prepared_facts["withdrawn"] = {"remaining":[],"owners":[42]}
    # An earlier peer source occupies the empty-strip route, so the
    # intentionally prepared offscreen source is the reuse candidate.
    prepared_facts["peer_floor"] = 8.0
    var same_prepared: Dictionary = Reservation.plan_facts(
        prepared_facts,"start",0.0,0.0,4.0,12.0)
    check(bool(same_prepared.get("ok",false)) and
        str(same_prepared.get("mode","")) == "reuse",
        "A prepared source is reused when the backend selects its exact existing slot")
    var later_prepared: Dictionary = Reservation.plan_facts(
        prepared_facts,"start",0.0,0.0,4.0,20.0)
    check(bool(later_prepared.get("ok",false)) and
        str(later_prepared.get("mode","")) == "append" and
        absf(float(later_prepared.get("start_world",0.0))-20.0) < .0001 and
        int(later_prepared.get("withdraw_owners",[]).size()) == 1,
        "A retractable READY strip yields to the exact later backend deadline")
    var paused_mismatch: Dictionary = prepared_facts.duplicate(true)
    paused_mismatch["online"] = [prepared.duplicate(true)]
    paused_mismatch["online"][0]["pending"] = false
    paused_mismatch["online"][0]["armed"] = true
    paused_mismatch["online"][0]["take_key"] = "active"
    paused_mismatch["was_paused"] = true
    paused_mismatch["last_take"] = "active"
    paused_mismatch["paused_owner"] = 42
    var paused_relocate: Dictionary = Reservation.plan_facts(
        paused_mismatch,"resume_fresh",0.0,0.0,4.0,20.0)
    check(not bool(paused_relocate.get("ok",false)) or
        str(paused_relocate.get("mode","")) != "reuse",
        "A genuinely paused authorized source cannot be moved to a new backend deadline")

    var armed: Dictionary = controller.arm_take(geometry(0.0),0.0,0.0,6.7,0.4,
        float(plan.start_world),false,4.0)
    check(not armed.is_empty(),"The physical source accepts the planned start")
    acknowledge(controller,0.0,"piece|7|10|practice","first")
    var original: Array = controller.online_snapshot()
    var music: Array = fixed_music(original)
    # Admit a second, unseen preparation; Pause must preserve exposed music.
    for item in controller.queue.online:
        item.segment.compiled = true
    controller.attach_compiled()
    for item in controller.queue.online:
        Lifecycle.project(item,2.0,330.0,100.0,20.0,Vector2(1000,600),4.0)
    var first: Dictionary = controller.queue.online[0]
    check(bool(first.get("ever_visible",false)),"The admitted source reaches the visible score")
    var before_x: float = first.clip.position.x+first.segment.position.x
    controller.observe_transport(geometry(2.0),2.0,0.0,0.0,"piece|7|10|practice","paused",true,false,true,"first",true)
    controller.observe_transport(geometry(2.5),2.5,0.0,0.0,"piece|7|10|practice","paused",true,false,true,"first",true)
    check(fixed_music(controller.online_snapshot()) == music,"Pause preserves every committed source and release boundary")
    Lifecycle.project(first,2.5,330.0,100.0,20.0,Vector2(1000,600),4.0)
    # This is a raw geometric projection at a later supplied world beat.
    # The owning presentation session freezes that input beat on Pause.
    check(first.clip.position.x+first.segment.position.x < before_x,
        "Source projects forward for increasing world time without moving its binding")
    var resume: Dictionary = Reservation.plan_facts(facts(controller,2.5),"resume_fresh",2.5,0.0,4.0)
    check(bool(resume.get("ok",false)) and str(resume.get("mode","")) == "append",
        "A frozen Resume reserves fresh future ink rather than retiming the paused take")
    controller.trim(geometry(2.5),"user_resume_fresh_replace_unseen",-1,
        int(resume.get("protected_strip",-1)))
    var resumed: Dictionary = controller.arm_take(geometry(2.5),2.5,0.0,6.7,0.4,
        float(resume.start_world),false,
        4.0 if bool(resume.get("empty_strip",false)) else 0.0,true)
    check(not resumed.is_empty(),"Resume commits its reserved source")
    acknowledge(controller,2.5,"piece|7|10|practice","resume")
    var after_resume: Array = controller.online_snapshot()
    check(fixed_music(after_resume).slice(0,1) == music.slice(0,1),
        "Resume preserves the original paused source while replacing its invisible rest")
    check(controller.visible_take_keys().has("piece|7|10|practice"),"Resume retains the attempt's performance identity")
    # Retry always allocates a future copy; it cannot re-anchor the old one.
    var retry: Dictionary = Reservation.plan_facts(facts(controller,3.0),"restart",3.0,0.0,4.0)
    check(bool(retry.get("ok",false)) and float(retry.first_pixel_x) > 1000.0
        and float(retry.start_world) >= 7.0,"Retry enters from the right after its count-in")
    controller.trim(geometry(3.0),"retry")
    controller.retry_placement_enabled(true)
    var restarted: Dictionary = controller.arm_take(geometry(3.0),3.0,0.0,6.7,0.4,
        float(retry.start_world),true,0.0,false,false,float(retry.get("leading_rest_beats",0.0)))
    check(not restarted.is_empty(),"Retry commits the future reservation")
    acknowledge(controller,3.0,"piece|7|11|practice","retry")
    check(fixed_music(controller.online_snapshot()).slice(0,1) == music.slice(0,1),
        "Retry preserves the original exposed source without relocating it")
    check(controller.visible_take_keys().has("piece|7|10|practice")
        and controller.visible_take_keys().has("piece|7|11|practice"),"Old and retried score copies keep separate results")
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
    # occupies the musical interval [8,12); the next attack is at 12.
    var auto_facts: Dictionary = facts(automatic_controller,9.0)
    var auto_plan: Dictionary = Reservation.plan_facts(
        auto_facts,"auto",9.0,0.0,4.0,12.0)
    check(bool(auto_plan.get("ok",false)),
        "Fixed one-bar repeat clears real retained written-rest ink")
    if bool(auto_plan.get("ok",false)):
        var next_armed: Dictionary = automatic_controller.arm_take(
            geometry(9.0),9.0,0.0,6.7,0.4,12.0,
            false,4.0,true)
        check(not next_armed.is_empty(),
            "A fixed one-bar repeat that passes physical preflight commits")
    automatic_canvas.free()

    # An already-printed rest is physical queue ink. A fixed Tempo repeat
    # must refuse overlap at preflight instead of passing the backend's
    # deadline to a queue that cannot commit it. The deadline cannot move.
    var repeat_facts := facts(controller,8.0)
    repeat_facts.online = [{"kind":"rest","world_origin":8.0,"source_floor":0.0,"source_ceiling":20.0}]
    repeat_facts.withdrawn = {"remaining":repeat_facts.online,"owners":[]}
    repeat_facts.peer_source_floor = -INF
    var repeat: Dictionary = Reservation.plan_facts(repeat_facts,"auto",8.0,0.0,4.0,12.0)
    check(not bool(repeat.get("ok",false)),
        "An exact Tempo repeat must refuse overlap with an admitted rest")
    repeat_facts.withdrawn.remaining = [{"kind":"source","world_origin":10.0,
        "source_floor":0.0,"source_ceiling":4.0}]
    check(not bool(Reservation.plan_facts(repeat_facts,"auto",8.0,0.0,4.0,12.0).get("ok",false)),
        "A direct repeat refuses overlap with exposed source ink")
    # Preserve the owner's 2026-11-18 Pathétique regression as measured
    # preflight facts, without a second renderer/queue implementation.
    var slow_world := 18.3153996732027
    var slow_header := 0.82415522875817
    var outgoing_rest_end := 18.5358163398694+2.0
    var slow_facts := {"ready":true,"duration":8.0,"density":288.0,"gap":22.0,
        "width":1256.0,"playhead":1256.0*0.33,"rest_gap":2.0,"bpm":16.0,
        "source_exists":true,"online":[],"withdrawn":{"remaining":[],"owners":[]},
        "peer_floor":outgoing_rest_end,"right":1256.0*0.67/288.0,
        "header":slow_header,"preview_world":slow_world}
    var slow: Dictionary = Reservation.plan_facts(slow_facts,"start",slow_world,0.0,2.0+0.4*16.0/60.0)
    check(bool(slow.get("ok",false)) and float(slow.first_pixel_x) > 1256.0
        and float(slow.start_world)-slow_header > outgoing_rest_end
        and float(slow.start_world) > 20.4215330065361,
        "First slow Tempo entry clears the outgoing written rest instead of using the refused deadline")
    var flow := Flow.new()
    flow.sample(1000,60.0)
    var previous: float = flow.sample(2000,60.0)
    check(flow.sample(3000,90.0) > previous and flow.sample(2500,90.0) >= previous,
        "Pause/retry handoffs and delayed frames cannot rewind the score world")
    flow.hold_at(flow.beat+1.0)
    flow.sample(10000,90.0)
    var held: float = flow.beat
    check(is_equal_approx(flow.project(20000),held),"Free holds the target while the learner thinks")
    flow.hold_at(held+1.0)
    check(flow.sample(21000,90.0) > held,"A correct Free target permits forward motion to the next target")
    canvas.free()
    print("SCORE_STREAM_FAILURES:",failures)
    quit(0 if failures == 0 else 1)
