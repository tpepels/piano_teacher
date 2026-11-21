extends RefCounted
## Sole owner of untimed Free's held visual source and admitted target plan.
## This is deliberately independent of graded playback admission: a Free
## note target holds the forward presentation axis until its MIDI condition
## is satisfied, and cannot create graded take/time policy.
var score_flow
var world := NAN
var source_from_beat := 0.0
var plan_id := ""
var source_fingerprint := ""
var source_revision := -1

func _init(flow) -> void:
    score_flow = flow

func update_hold(state: Dictionary) -> void:
    # This is a renderer cache for ONE immutable source revision. A new
    # practice window can enter Free directly without passing through a
    # timed/idle mode; retaining its old plan would hold wrong notes.
    var next_fingerprint: String = str(state.get("piece_fingerprint",""))
    var next_revision: int = int(state.get("revision",-1))
    if (source_fingerprint != next_fingerprint
            or source_revision != next_revision):
        source_fingerprint = next_fingerprint
        source_revision = next_revision
        world = NAN
        source_from_beat = 0.0
        plan_id = ""
    var directive: Variant = state.get("presentation_directive",{})
    # A state without an explicit backend directive cannot authorize
    # motion. Default to a frozen visible world rather than a native
    # phase/BPM heuristic that might move unadmitted notation.
    var kind: String = str(directive.get("kind","hold")) \
        if directive is Dictionary else "hold"
    match kind:
        "hold":
            score_flow.hold_at(score_flow.project(maxi(0,score_flow.last_ms)))
            return
        "retain":
            # Preserve the previous hold (if any) while the backend
            # prepares the next source. An outstanding intent alone
            # cannot release the painted Pause/Free target.
            return
        "target":
            if not is_finite(world):
                score_flow.hold_at(score_flow.project(maxi(0,score_flow.last_ms)))
                return
            var beat: float = float(directive.get("source_beat",NAN))
            if is_finite(beat):
                score_flow.hold_at(world+maxf(0.0,beat-source_from_beat))
            return
        "run":
            if bool(directive.get("clear_target",false)):
                world = NAN
                plan_id = ""
            score_flow.release_hold()
            return
        _:
            push_error("Unknown backend score presentation directive: "+kind)
            score_flow.hold_at(score_flow.project(maxi(0,score_flow.last_ms)))


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
    var key: String = str(guided["plan_id"])
    if key.is_empty() or (key == plan_id and is_finite(world)):
        return
    var target_world: float = score_flow.project_authored_future(
        deadline,received_ms,clock_beat,
        float(parsed.get("bpm",40.0)),[])
    if not is_finite(target_world) or target_world <= visual_world:
        # Free notes must be admitted strictly ahead of the playhead.
        # An expired target cannot be made visible by shifting ink.
        return
    var admitted: bool = renderer.enqueue_recovery_queue(
        visual_world,float(guided["source_from_beat"]),
        target_world,str(guided["plan_id"]),true,
        float(guided.get("count_in_beats",0.0)),
        false,true,preload("res://note_status_registry.gd").take_key(parsed))
    if not admitted:
        return
    var admitted_world: float = renderer.scheduled_plan_opening(key)
    if is_finite(admitted_world):
        world = admitted_world
        source_from_beat = float(guided["source_from_beat"])
        plan_id = key
