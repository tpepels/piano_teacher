extends RefCounted
## Sole owner of untimed Free's held visual source and admitted target plan.
## This is deliberately independent of graded playback admission: a Free
## note target holds the forward presentation axis until its MIDI condition
## is satisfied, and cannot create graded take/time policy.
var score_flow
var world := NAN
var source_from_beat := 0.0
var plan_id := ""

func _init(flow) -> void:
    score_flow = flow

func update_hold(state: Dictionary) -> void:
    var guided: bool = str(state.get("mode","")) == "learn" and \
        str(state.get("phase","")).begins_with("guided") and is_finite(world)
    if not guided:
        if str(state.get("mode","")) != "learn":
            world = NAN
            plan_id = ""
        score_flow.release_hold()
        return
    var teaching: Variant = state.get("teaching")
    var expected: Array = teaching.get("expected_notes",[]) \
        if teaching is Dictionary else []
    if expected.is_empty():
        # Completed Free target remains under the stationary playhead
        # until the next course decision is authorized.
        return
    var target: float = INF
    for note in expected:
        if note is Dictionary and note.has("beat"):
            target = minf(target,float(note["beat"]))
    if is_finite(target):
        score_flow.hold_at(world+maxf(0.0,target-source_from_beat))

func publish_authorized_target(parsed: Dictionary, renderer,
        visual_world: float, received_ms: int,
        backend_offset_ms: float, clock_beat: float) -> void:
    var active: Variant = parsed.get("playback_timeline")
    var guided: Variant = active.get("guided") if active is Dictionary else null
    if str(parsed.get("mode","")) != "learn" or \
            not guided is Dictionary or \
            not bool(parsed.get("loaded",false)) or \
            bool(parsed.get("paused",false)):
        return
    if not (guided.has("deadline_at_ms") and \
            guided.has("source_from_beat") and guided.has("plan_id")):
        return
    if not is_finite(backend_offset_ms):
        return
    var deadline: int = roundi(float(guided["deadline_at_ms"])+backend_offset_ms)
    var target_world: float = score_flow.project_authored_future(
        deadline,received_ms,clock_beat,
        float(parsed.get("bpm",40.0)),[])
    var admitted: bool = renderer.enqueue_recovery_queue(
        visual_world,float(guided["source_from_beat"]),
        target_world,str(guided["plan_id"]),true,
        float(guided.get("count_in_beats",0.0)),
        false,true)
    if not admitted:
        return
    var key: String = str(guided["plan_id"])
    if renderer.scheduled_plan_openings.has(key):
        world = float(renderer.scheduled_plan_openings[key])
        source_from_beat = float(guided["source_from_beat"])
        plan_id = key
