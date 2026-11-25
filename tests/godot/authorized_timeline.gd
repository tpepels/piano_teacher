extends SceneTree
## V1/V4 frame-stepped projection checks using the production timeline,
## guided target holder and physical measurement ports. No duplicate
## movement, scheduling or teaching state machine is constructed.
const Flow := preload("res://continuous_score_flow.gd")
const Guided := preload("res://guided_presentation_session.gd")
var failures := 0

func check(ok: bool, label: String) -> void:
    if not ok:
        failures += 1
        printerr("AUTHORIZED_TIMELINE_FAIL: ",label)

func near(a: float, b: float, tolerance: float = .02) -> bool:
    return is_finite(a) and is_finite(b) and absf(a-b) <= tolerance

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    # Outside a run the staff stands still.
    var flow := Flow.new()
    flow.sample(1000,60.0)
    var first := flow.project(1000)
    flow.sample(4000,60.0)
    check(near(flow.project(4000),first) and near(flow.project(7000),first),
        "Idle world stays where it is")

    # Free on the timeline: travel to the first target, hold, move on.
    var free := Flow.new()
    free.backend_clock = func(): return float(Time.get_ticks_msec())
    var f0: float = float(Time.get_ticks_msec())
    var free_state := {"run":7,"end_world":null,"holds_ms":[],"next_take":null,"segments":[
        {"kind":"rest","world_start":0.0,"start_ms":f0,"beats":2.0,
            "spans":[[2.0,60.0,60.0]],"hold_ms":null},
        {"kind":"hold","world_start":2.0,"start_ms":f0+2000.0,"beats":0.0,
            "spans":[[0.0,60.0,60.0]],"hold_ms":null}]}
    free.follow(free_state,int(f0))
    check(near(free.project(int(f0)+1000),1.0,.03),"Free travels to its first target")
    free.sample(int(f0)+9000)
    check(near(free.project(int(f0)+9000),2.0,.03) and near(free.hold_world,2.0,.03),
        "Free holds the target at the playhead while the learner thinks")
    free_state["segments"][1]["hold_ms"] = 9000.0
    free_state["segments"].append({"kind":"rest","world_start":2.0,"start_ms":f0+11000.0,
        "beats":1.0,"spans":[[1.0,60.0,60.0]],"hold_ms":null})
    free_state["segments"].append({"kind":"hold","world_start":3.0,"start_ms":f0+12000.0,
        "beats":0.0,"spans":[[0.0,60.0,60.0]],"hold_ms":null})
    free.follow(free_state,int(f0)+9000)
    check(near(free.project(int(f0)+11500),2.5,.03) and near(free.project(int(f0)+20000),3.0,.03),
        "A played target moves the staff on to the next one and holds again")

    # A run of timed music: the world follows the published timeline.
    # Godot's clock stands in for the backend clock here (offset zero).
    var running := Flow.new()
    running.backend_clock = func(): return float(Time.get_ticks_msec())
    var t0: float = float(Time.get_ticks_msec())
    running.sample(int(t0),60.0)
    var start_world: float = running.project(int(t0))
    var run_state := {"run":1,"end_world":null,"holds_ms":[],"segments":[
        {"kind":"count_in","world_start":0.0,"start_ms":t0+1000.0,"beats":4.0,
            "spans":[[2.0,60.0,120.0],[2.0,120.0,120.0]],"take_id":"",
            "mode":"","source_from_beat":0.0,"meter":[4,4]},
        {"kind":"take","world_start":4.0,"start_ms":t0+1000.0+(120.0/sqrt(60.0*120.0)+1.0)*1000.0,
            "beats":4.0,"spans":[[4.0,120.0,120.0]],"take_id":"take:1",
            "mode":"practice","source_from_beat":0.0,"meter":[4,4]}]}
    running.follow(run_state,int(t0))
    check(running.following and near(running.project(int(t0)+500),start_world),
        "A new run starts from the world where the staff stands")
    var ramp_end_ms: float = t0+1000.0+120.0/sqrt(60.0*120.0)*1000.0
    check(near(running.project(int(ramp_end_ms)),start_world+2.0,.03),
        "The eased first half of the count-in covers exactly two beats")
    var take_ms: float = float(run_state["segments"][1]["start_ms"])
    check(near(running.project(int(take_ms)),start_world+4.0,.03),
        "The take's first beat reaches the playhead at its timeline time")
    check(near(running.project(int(take_ms)+1000),start_world+6.0,.03),
        "The take scrolls at its own tempo")
    var paused_state: Dictionary = run_state.duplicate(true)
    paused_state["holds_ms"] = [[take_ms+500.0,null]]
    running.sample(int(take_ms)+400)
    running.follow(paused_state,int(take_ms)+400)
    check(near(running.project(int(take_ms)+5000),start_world+5.0,.03),
        "Pause freezes the timeline world")
    running.follow(null,int(take_ms)+600)
    check(not running.following and near(running.project(int(take_ms)+9000),running.beat),
        "After the run the world holds where the run left it")


    var guided := Guided.new(flow)
    guided.world = 100.0
    guided.source_from_beat = 0.0
    guided.plan_id = "stale:1"
    guided.source_fingerprint = "old"
    guided.source_revision = 1
    guided.update_hold({
        "loaded":true,"mode":"learn","phase":"guided_wait",
        "paused":false,"piece_fingerprint":"new","revision":2,
        "teaching":{"expected_notes":[{"beat":0.0}]}
    })
    check(guided.plan_id.is_empty() and not is_finite(guided.world),
        "New practice source cannot reuse a prior Free target binding")

    print("AUTHORIZED_TIMELINE_FAILURES:",failures)
    quit(0 if failures == 0 else 1)
