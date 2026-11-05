extends SceneTree
## Real present_flow / retained-note projection regression. A backend Play
## response is forbidden to allocate new notes or change the world origin.
const Admission := preload("res://score_stream_admission.gd")
class FakeSegment:
    extends Node2D
    var compiled := true
    var note_instances: Array = []
class InstrumentedView:
    extends "res://notation/native/view.gd"
    var admissions: Array = []
    func retained_ready() -> bool:
        return true
    func _stream_add_take(source_beat: float, start_world: float,
            from_beat: float, through_beat: float, take_key: String) -> void:
        var clip := Control.new()
        clip.clip_contents = true
        add_child(clip)
        var segment := FakeSegment.new()
        clip.add_child(segment)
        for i in range(8):
            segment.note_instances.append({
                "event_id":"attack-%d" % i,
                "source_id":"source-%d" % i,
                "position":Vector2(float(i)*96.0,200.0)})
        _stream_serial += 1
        admissions.append({"world":start_world,"serial":_stream_serial})
        stream_passes.append({"segment":segment,"clip":clip,
            "world_origin":start_world-source_beat,
            "source_floor":from_beat,"source_ceiling":through_beat,
            "take_key":take_key,"pending":take_key in ["prepared","autopending"],
            "serial":_stream_serial})
var failures := 0
func check(ok: bool, message: String) -> void:
    if not ok:
        failures += 1
        print("STREAM_PROJECTED_OVERLAP_FAILED:",message)
func _initialize() -> void:
    var v := InstrumentedView.new()
    v.size = Vector2(800,440)
    v.native_ready = true
    v.timeline.duration_beats = 8
    v.timeline.measures = [{"start_beat":0.0,"end_beat":4.0},
        {"start_beat":4.0,"end_beat":8.0}]
    v.timeline.pixels_per_beat = 96.0
    var state: Dictionary = {"running":false,"paused":false,
        "phase":"ready","mode":"practice","piece_fingerprint":"score",
        "revision":1,"transport_id":0,"play_from_beat":0.0}
    var world := 0.0
    v.present_flow(world,state,0)
    check(v.admissions.size()==1,
        "Ready prepositions score without any Play event")
    var initial_origin: float = float(v.stream_passes[0]["world_origin"])
    check(initial_origin > v._stream_right_beats()+v._stream_header_beats(0.0),
        "initial source/clef begin completely outside the viewport")
    var prepared: Dictionary = v.arm_stream_take(world,0.0)
    check(not prepared.is_empty(),"user Play binds the reserved source")
    var count := v.admissions.size()
    state["phase"]="count_in"
    state["running"]=true
    state["transport_id"]=1
    v.present_flow(world,state,-float(prepared["start_world"]))
    check(v.admissions.size()==count,
        "the actual Play state transition cannot add notes")
    state["paused"]=true
    state["phase"]="paused"
    v.present_flow(world+.1,state,-float(prepared["start_world"]))
    var live_count: int = v.admissions.size()
    var unchanged: Dictionary = v.arm_stream_take(world+.1,0.0,NAN,true)
    check(bool(unchanged.get("reused",false)) and
            v.admissions.size()==live_count,
        "Pause before the first source note must not create a duplicate")
    state["paused"]=false
    state["phase"]="count_in"
    v.present_flow(world+.1,state,-float(prepared["start_world"]))
    check(is_equal_approx(float(v.stream_passes[0]["world_origin"]),initial_origin),
        "the Play state transition cannot seek or move the score")
    var previous_x := INF
    for frame in range(120):
        world += .12
        v.present_flow(world,state,world-float(prepared["start_world"]))
        v.drawn_note_instances.clear()
        v.drawn_noteheads.clear()
        v.fingering_pass_clocks.clear()
        v._project_stream(v.size.x*.33)
        var current_x := v.size.x*.33+(initial_origin-world)*96.0
        check(current_x <= previous_x+.0001,
            "all frames share the exact forward-only world axis")
        previous_x = current_x
        if frame==20:
            state["paused"]=true
            state["phase"]="paused"
            count = v.admissions.size()
        if bool(state["paused"]):
            check(v.admissions.size()==count,
                "Pause never admits extra notes, even after many frames")
        if frame==44:
            var resume: Dictionary = v.arm_stream_take(world,3.0)
            check(not resume.is_empty(),
                "Resume reserves an entirely new copy offscreen")
            var next: Dictionary = v.stream_passes[-1]
            check(float(next["world_origin"])+3.0 >
                world+v._stream_right_beats(),
                "resumed source may not pop inside the visible frame")
            state["paused"]=false
            state["phase"]="count_in"
        for i in range(v.drawn_note_instances.size()):
            var a: Dictionary = v.drawn_note_instances[i]
            for j in range(i+1,v.drawn_note_instances.size()):
                var b: Dictionary = v.drawn_note_instances[j]
                if int(a["pass_index"])==int(b["pass_index"]):
                    continue
                check(absf(float(a["position"].x)-float(b["position"].x))>=12.0,
                    "two source copies may never overlap a notehead")
    # A later manual Resume or Retry consumes any still-offscreen automatic
    # passage instead of stacking another future duplicate.
    var future_world: float = world+65.0
    v._stream_add_take(0.0,future_world,0.0,8.0,"autopending")
    var auto_serial: int = v._stream_serial
    var previous_count: int = v.admissions.size()
    var reused: Dictionary = v.arm_stream_take(world,3.0,NAN,true)
    check(bool(reused.get("reused",false)) and
            v._stream_serial == auto_serial and
            v.admissions.size() == previous_count,
        "manual Resume reuses future auto ink rather than duplicating notes")
    var retained_origin := false
    for item in v.stream_passes:
        if int(item["serial"]) == auto_serial:
            retained_origin = is_equal_approx(float(item["source_floor"]),3.0) and \
                is_equal_approx(float(item["world_origin"]),future_world)
    check(retained_origin,
        "repurposed source preserves world position and hides earlier noteheads")
    v.free()
    # READY remains empty indefinitely: the first offscreen retained
    # source is recycled, rather than accumulating ghost notes after idle.
    var idle := InstrumentedView.new()
    idle.size = Vector2(800,440)
    idle.native_ready = true
    idle.timeline.duration_beats = 8.0
    idle.timeline.measures = [{"start_beat":0.0,"end_beat":4.0},
        {"start_beat":4.0,"end_beat":8.0}]
    idle.timeline.pixels_per_beat = 96.0
    var ready_state: Dictionary = {"running":false,"paused":false,
        "phase":"ready","mode":"practice","piece_fingerprint":"idle",
        "revision":2,"transport_id":0,"play_from_beat":0.0}
    for tick in range(350):
        var idle_world: float = tick*.12
        idle.present_flow(idle_world,ready_state,0)
        idle.drawn_note_instances.clear()
        idle.drawn_noteheads.clear()
        idle.fingering_pass_clocks.clear()
        idle._project_stream(idle.size.x*.33)
        check(idle.admissions.size()==1,
            "READY cannot add a new source copy while the bar moves")
        check(idle.drawn_noteheads.is_empty(),
            "READY must not display idle noteheads without Play")
        var reserve: Dictionary = idle.stream_passes[0]
        var threshold: float = idle_world+idle._stream_right_beats()+ \
            idle._stream_header_beats(0.0)
        check(float(reserve["world_origin"]) > threshold,
            "READY must reposition hidden source before its header enters view")
    var idle_armed: Dictionary = idle.arm_stream_take(idle.stream_world_beat,0)
    check(not idle_armed.is_empty() and idle.admissions.size()==1,
        "Play must claim the single already engraved idle reservation")
    idle.free()
    print("STREAM_PROJECTED_OVERLAP_FAILURES:",failures)
    quit(0 if failures==0 else 1)
