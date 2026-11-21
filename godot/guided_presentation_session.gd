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
    if bool(state.get("paused",false)):
        # A pending Resume intent is not authorization. Physical future
        # geometry may be forecast without releasing the visible hold.
        score_flow.hold_at(score_flow.project(maxi(0,score_flow.last_ms)))
        return
    # These are all states of the same untimed Free exposure; losing MIDI
    # or briefly introducing the passage must not release its target hold.
    var guided: bool = str(state.get("mode","")) == "learn" and \
        str(state.get("phase","")) in [
            "guided_wait", "introducing", "disconnected", "guided_complete"
        ]
    # The backend can select a timed mode while its source is still
    # unadmitted. Keep the Free canvas held until physical authorization.
    var pending: Variant = state.get("playback_intent")
    if not guided and pending is Dictionary and \
            not pending.is_empty() and is_finite(score_flow.hold_world):
        return
    if not guided:
        if str(state.get("mode","")) != "learn":
            world = NAN
            plan_id = ""
        score_flow.release_hold()
        return
    if not is_finite(world):
        # Free must remain stationary before its first target or MIDI
        # event, even while pre-engraving/readiness is outstanding.
        score_flow.hold_at(score_flow.project(maxi(0,score_flow.last_ms)))
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
        false,true,preload("res://note_status_registry.gd").take_key(parsed))
    if not admitted:
        return
    var key: String = str(guided["plan_id"])
    var admitted_world: float = renderer.scheduled_plan_opening(key)
    if is_finite(admitted_world):
        world = admitted_world
        source_from_beat = float(guided["source_from_beat"])
        plan_id = key
