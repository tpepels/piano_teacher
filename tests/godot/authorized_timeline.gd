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
    var flow := Flow.new()
    flow.sample(1000,60.0)
    var first := flow.project(1000)
    flow.hold_at(first)
    flow.sample(4000,60.0)
    check(near(flow.project(4000),first) and near(flow.project(7000),first),
        "Free/paused world remains painted at its original held coordinate")
    var physical: float = flow.physical_travel_ms_to(
        first+4.0,4000,0.0,60.0,[])
    check(near(physical,4000.0,.1),
        "Held constant-tempo score reports exact future physical travel")
    var future: float = flow.project_authored_future(8000,4000,0.0,60.0,[])
    check(near(future,first+4.0),
        "Future admission forecast does not obey the painted Pause hold")
    check(near(flow.project(8000),first),
        "A candidate forecast cannot expose notes or release Pause")

    var shaped: Array = [
        {"start_beat":0.0,"end_beat":2.0,"bpm":60.0},
        {"start_beat":2.0,"end_beat":4.0,"bpm":120.0}
    ]
    check(near(flow.physical_travel_ms_to(
        first+4.0,4000,0.0,60.0,shaped),3000.0,.1),
        "Held authored slow/fast source integrates by tempo epochs")
    check(near(flow.project_authored_future(
        7000,4000,0.0,60.0,shaped),first+4.0),
        "Hypothetical variable tempo and physical inverse agree")

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

    var unbound := Flow.new()
    unbound.sample_uncommitted(1000,72.0)
    check(near(unbound.timeline.current_rate(),72.0),
        "Unbound first source can still initialize its own projected rate")

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
