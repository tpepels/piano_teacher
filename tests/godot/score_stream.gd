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
    var next_armed: Dictionary = automatic_controller.place_timeline_take(
        geometry(9.0),0.0,12.0,6.7,0.4,4.0)
    check(not next_armed.is_empty(),
        "A one-bar repeat after the written rest is drawn at its timeline place")
    var overlapping: Dictionary = automatic_controller.place_timeline_take(
        geometry(13.0),0.0,14.0,6.7,0.4,4.0)
    check(overlapping.is_empty(),"A take may never overlap ink already drawn")
    automatic_canvas.free()

    # A take whose first note never reached the playhead is withdrawn when
    # a new run places its own take (e.g. Listen abandoned for Tempo).
    var abandon_controller := Controller.new()
    var abandon_pool := Pool.new()
    var abandon_canvas := Control.new()
    root.add_child(abandon_canvas)
    abandon_pool.install(abandon_canvas,windows)
    abandon_controller.bind_surface(abandon_canvas,abandon_pool,
        func(_beat: float) -> Array[Vector2]: return windows)
    check(not abandon_controller.place_timeline_take(geometry(0.0),0.0,4.0,6.7,0.4,4.0).is_empty(),
        "The first exposure is drawn")
    check(abandon_controller.ink_end(geometry(0.5)) == -INF,
        "Unplayed ink does not delay the next run")
    check(not abandon_controller.place_timeline_take(geometry(0.5),0.0,5.0,6.7,0.4,4.0).is_empty()
        and abandon_controller.online_snapshot().filter(
            func(i): return str(i.get("kind","")) == "source").size() == 1,
        "The abandoned unplayed take makes way for the new one")
    abandon_canvas.free()
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
