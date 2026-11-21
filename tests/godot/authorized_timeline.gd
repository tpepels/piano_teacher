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

    flow.authorize_source_epoch(8000,0.0,60.0,[],"take:1")
    check(near(flow.project(4500),first),
        "A backend-authorized future epoch does not release Pause")
    flow.sample(4500)
    flow.release_hold()
    var resumed := flow.project(4800)
    check(resumed >= first and resumed < first+4.0,
        "Resuming preserves continuous non-reversing presentation time")
    check(flow.timeline.active_segment == "take:1",
        "Authorized source identity survives the native Pause release")

    var running := Flow.new()
    running.sample(1000,60.0)
    running.authorize_source_epoch(2000,0.0,60.0,shaped,"shaped:1")
    running.sample(2000)
    var at_first: float = running.project(2000)
    check(near(running.physical_travel_ms_to(
        at_first+4.0,2000,0.0,60.0,shaped),3000.0,.1),
        "Unheld physical inverse integrates the committed tempo epochs")
    var advanced := running.sample(5000)
    check(near(advanced,at_first+4.0),
        "The committed source reaches the authored four-beat position")
    check(running.sample(4200) >= advanced,
        "Late state frames cannot rewind the authorized world")

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
