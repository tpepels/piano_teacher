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
    func _new_retained_segment(kind: String):
        var segment := FakeSegment.new()
        add_child(segment)
        retained_all_segments.append(segment)
        if kind == "source":
            for i in range(8):
                segment.note_instances.append({
                    "event_id":"attack-%d" % i,
                    "source_id":"source-%d" % i,
                    "position":Vector2(float(i)*96.0,200.0)})
        return segment
    func _stream_add_take(source_beat: float, start_world: float,
            from_beat: float, take_key: String) -> void:
        var before: int = _stream_serial
        # Test the REAL online/offline queue. Only immutable retained DRAW
        # buffers are replaced by in-memory dummy glyphs.
        super._stream_add_take(source_beat,start_world,from_beat,take_key)
        if _stream_serial > before:
            admissions.append({"world":start_world,"serial":_stream_serial})

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
    var outside_snapshot: Array = v.stream_passes
    outside_snapshot[0]["world_origin"] = -999.0
    outside_snapshot.clear()
    check(v.stream_passes.size()>=1 and
        is_equal_approx(float(v.stream_passes[0]["world_origin"]),initial_origin),
        "external HUD or debug readers cannot mutate queued note positions or dequeue ink")
    check(initial_origin > v._stream_right_beats()+v._stream_header_beats(0.0),
        "initial source/clef begin completely outside the viewport")
    # An idle reservation must remain fixed over ordinary animation frames;
    # it may be safely retimed only after approaching the offscreen boundary.
    v.present_flow(world+.2,state,0)
    check(is_equal_approx(float(v.stream_passes[0]["world_origin"]),initial_origin),
        "READY notes must travel rather than being retimed on every frame")
    var prepared: Dictionary = v.arm_stream_take(world+.2,0.0)
    check(not prepared.is_empty(),"user Play binds the reserved source")
    var count := v.admissions.size()
    # The last READY snapshot remains active while the command is in flight.
    # That frame may not generate a duplicate future passage.
    v.present_flow(world+.2,state,0)
    check(v.admissions.size()==count and
        is_equal_approx(float(v.stream_passes[0]["world_origin"]),initial_origin),
        "an armed Play cannot create a second READY score or move its ink")
    state["phase"]="count_in"
    state["running"]=true
    state["transport_id"]=1
    v.present_flow(world,state,-float(prepared["start_world"]))
    check(v._stream_armed_serial == int(v.stream_passes[0]["serial"]) and
        v._stream_last_take.is_empty(),
        "unacknowledged polling cannot bind an armed Play to a stale transport")
    check(v.acknowledge_stream_arm(),
        "successful backend Play response authorizes transport binding")
    v.present_flow(world,state,-float(prepared["start_world"]))
    check(v._stream_last_take == "score|1|1|practice" and
        v._stream_armed_serial == -1,
        "an acknowledged Play binds its unique source and clears provisional state")
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
    check(v.acknowledge_stream_arm(),"backend Resume acknowledgement is required")
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
            if not resume.is_empty():
                v.acknowledge_stream_arm()
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
    # A pre-engraved automatic attempt for beat zero cannot be reused
    # for a Resume at beat three. Its immutable content is archived offline
    # and a distinct source owner is appended after the locked prefix.
    var future_world: float = world+65.0
    v._stream_add_take(0.0,future_world,0.0,"autopending")
    var old_auto: int = v._stream_serial
    var original_auto_floor: float = float(v.stream_passes[-1]["source_floor"])
    var withdrawn: Array[int] = v.trim_future_queue(
        "resume_different_opening")
    check(withdrawn.has(old_auto) and
        not v.stream_passes.any(func(item: Dictionary) -> bool:
            return int(item.get("serial",0)) == old_auto),
        "incompatible future automatic copy leaves the online tail")
    var archive_has_auto := false
    for record in v.offline_stream_queue:
        if int(record.get("owner_serial",-1)) == old_auto and \
                str(record.get("event","")) == "withdrawn":
            archive_has_auto = (
                is_equal_approx(float(record["plan"][0]["source_floor"]),
                    original_auto_floor))
    check(archive_has_auto,
        "withdrawn source is retained offline with unchanged authored notes")
    var prior_admissions: int = v.admissions.size()
    var resumed: Dictionary = v.arm_stream_take(world,3.0,NAN,true)
    check(not resumed.is_empty() and
        v.admissions.size() == prior_admissions+1,
        "Resume appends one new immutable source after withdrawing old future")
    var next_owner: int = v._stream_last_admitted
    var next_opening_found: bool = v.stream_passes.any(
        func(item: Dictionary) -> bool:
            return int(item.get("take_owner",-1))==next_owner and \
                absf(float(item.get("source_floor",-1))-3.0)<.00001)
    check(next_owner > old_auto and next_opening_found,
        "new Resume owner has the correct source opening")
    check(v.cancel_stream_arm() and
        not v.stream_passes.any(func(item: Dictionary) -> bool:
            return int(item.get("serial",0)) == next_owner),
        "failed new Resume is withdrawn atomically without changing history")
    v.free()
    # A READY strip may have reached the visible boundary while the app
    # processes Pause -> Resume. Visible old ink is immutable, but it must
    # NEVER prevent an entirely new take being placed further in the future.
    var stale := InstrumentedView.new()
    stale.size = Vector2(800,440)
    stale.native_ready = true
    stale.timeline.duration_beats = 8.0
    stale.timeline.measures = [{"start_beat":0.0,"end_beat":4.0},
        {"start_beat":4.0,"end_beat":8.0}]
    stale.timeline.pixels_per_beat = 96.0
    stale.present_flow(0.0,{"running":false,"paused":false,
        "phase":"ready","mode":"practice","piece_fingerprint":"stale",
        "revision":1,"transport_id":0,"play_from_beat":0.0},0.0)
    var old_stale_origin: float = float(stale.stream_passes[0]["world_origin"])
    stale._stream_queue.online[0]["ever_visible"] = true
    var recovered: Dictionary = stale.arm_stream_take(4.0,0.0,NAN,true)
    check(not recovered.is_empty(),
        "Resume cannot reject a loaded score because its READY tail is already exposed")
    check(is_equal_approx(float(stale.stream_passes[0]["world_origin"]),
            old_stale_origin) and
        float(recovered.get("start_world",-INF)) > old_stale_origin+8.0,
        "exposed old notation is unchanged and fresh Resume ink stays in the future")
    stale.free()
    # Pausing in the middle of a measure changes the requested source
    # opening. No earlier measure strip can be reused under that identity.
    var middle := InstrumentedView.new()
    middle.size = Vector2(800,440)
    middle.native_ready = true
    middle.timeline.duration_beats = 8.0
    middle.timeline.measures = [{"start_beat":0.0,"end_beat":4.0},
        {"start_beat":4.0,"end_beat":8.0}]
    middle.timeline.pixels_per_beat = 96.0
    middle.present_flow(0.0,{"running":false,"paused":false,
        "phase":"ready","mode":"practice","piece_fingerprint":"middle",
        "revision":1,"transport_id":0,"play_from_beat":0.0},0.0)
    var middle_arm: Dictionary = middle.arm_stream_take(.1,0.0)
    check(not middle_arm.is_empty() and middle.acknowledge_stream_arm(),
        "mid-measure fixture starts with an acknowledged score")
    var middle_state: Dictionary = {"running":true,"paused":false,
        "phase":"playing","mode":"practice","piece_fingerprint":"middle",
        "revision":1,"transport_id":1,"play_from_beat":0.0}
    middle.present_flow(.2,middle_state,3.25)
    middle_state["paused"] = true
    middle_state["phase"] = "paused"
    middle.present_flow(.3,middle_state,3.25)
    var earlier_count: int = middle.admissions.size()
    var mid_resume: Dictionary = middle.arm_stream_take(.4,3.25,NAN,true)
    check(not mid_resume.is_empty() and middle.admissions.size() == earlier_count+1,
        "Resume in the middle of a measure enqueues a distinct future source")
    check(middle.stream_passes.any(func(item: Dictionary) -> bool:
        return (str(item.get("kind",""))=="source" and
            absf(float(item.get("source_floor",-1.0))-3.25)<.00001)),
        "the new passage begins at the exact resumed musical position")
    middle.free()
    # Pause can arrive after backend Play but BEFORE the first running
    # snapshot binds its source to the transport key. The two queued measure
    # strips still belong to the current attempt and are NEVER speculative.
    var racing := InstrumentedView.new()
    racing.size = Vector2(800,440)
    racing.native_ready = true
    racing.timeline.duration_beats = 8.0
    racing.timeline.measures = [{"start_beat":0.0,"end_beat":4.0},
        {"start_beat":4.0,"end_beat":8.0}]
    racing.timeline.pixels_per_beat = 96.0
    var race_state: Dictionary = {
        "running":false,"paused":false,"phase":"ready",
        "mode":"practice","piece_fingerprint":"race","revision":1,
        "transport_id":0,"play_from_beat":0.0}
    racing.present_flow(0.0,race_state,0.0)
    check(racing.stream_passes.size()==2,
        "READY preloads the entire logical take as two immutable strips")
    var race_origin: float = float(racing.stream_passes[0]["world_origin"])
    var race_arm: Dictionary = racing.arm_stream_take(.01,0.0)
    check(not race_arm.is_empty(),"Play arms one full logical take")
    race_state["running"] = true
    race_state["phase"] = "count_in"
    race_state["transport_id"] = 1
    racing.present_flow(.10,race_state,0.0)
    check(racing._stream_live_serial == -1 and
        racing._stream_armed_serial > 0,
        "unacknowledged backend Play has an armed but not yet live take")
    race_state["paused"] = true
    race_state["phase"] = "paused"
    racing.present_flow(.20,race_state,0.0)
    check(racing.stream_passes.size()==2 and
        racing._stream_paused_owner==1 and
        racing.stream_passes.all(func(item: Dictionary) -> bool:
            return int(item.get("take_owner",-1))==1 and \
                is_equal_approx(float(item["world_origin"]),race_origin)),
        "Pause cannot retract the in-flight, unexposed source strips")
    racing.trim_resume_speculation(.21,0.0)
    check(racing.stream_passes.size()==2 and
        racing._stream_queue.has_take(1),
        "Resume must not treat the paused take as an incompatible successor")
    check(racing.acknowledge_stream_arm(),
        "late Play acknowledgement can still bind its retained source")
    race_state["paused"] = false
    race_state["phase"] = "count_in"
    racing.present_flow(.22,race_state,0.0)
    check(racing._stream_live_serial==1 and
        racing.stream_passes.size()==2 and
        racing.stream_passes.all(func(item: Dictionary) -> bool:
            return str(item.get("take_key",""))=="race|1|1|practice"),
        "late-acknowledged Resume preserves and binds all original strips")
    # A later paused snapshot can lose its transient _stream_live_serial.
    # The committed transport ID remains sufficient to protect its ink.
    racing._stream_live_serial = -1
    race_state["paused"] = true
    race_state["phase"] = "paused"
    racing.present_flow(.23,race_state,0.0)
    check(racing._stream_paused_owner==1 and
        racing._stream_queue.has_take(1),
        "Pause resolves an existing source from its bound transport key")
    racing._stream_add_take(0.0,40.0,0.0,"autopending")
    var race_future: int = racing._stream_serial
    check(racing._stream_queue.has_take(racing._stream_last_admitted),
        "fixture includes a genuinely speculative future take")
    racing.trim_resume_speculation(.24,3.0)
    check(racing.stream_passes.is_empty() and
        not racing._stream_queue.has_take(1) and
        not racing._stream_queue.has_take(race_future),
        "changed-opening Resume withdraws all safe, still-unseen old music")
    var archived_paused := false
    for event in racing._stream_queue.history:
        if (int(event.get("owner_serial",-1)) == 1 and
                str(event.get("event","")) == "withdrawn"):
            archived_paused = true
    check(archived_paused,
        "retracted acknowledged music is retained offline instead of lost")
    racing.free()
    # Long-passage Pause/Resume must not wait for the entire previously
    # queued exercise to scroll away. Only the first VISIBLE strip locks.
    var long_take := InstrumentedView.new()
    long_take.size = Vector2(800,440)
    long_take.native_ready = true
    long_take.timeline.duration_beats = 16.0
    long_take.timeline.measures = [
        {"start_beat":0.0,"end_beat":4.0},
        {"start_beat":4.0,"end_beat":8.0},
        {"start_beat":8.0,"end_beat":12.0},
        {"start_beat":12.0,"end_beat":16.0}]
    long_take.timeline.pixels_per_beat = 96.0
    var long_state: Dictionary = {
        "running":false,"paused":false,"phase":"ready","mode":"practice",
        "piece_fingerprint":"long","revision":1,"transport_id":0,
        "play_from_beat":0.0}
    long_take.present_flow(0.0,long_state,0.0)
    var initial_long: Dictionary = long_take.arm_stream_take(0.0,0.0)
    check(not initial_long.is_empty() and long_take.acknowledge_stream_arm(),
        "long source prepares and binds the original four-measure take")
    var original_long_origin: float = float(
        long_take.stream_passes[0]["world_origin"])
    long_state["running"] = true
    long_state["phase"] = "count_in"
    long_state["transport_id"] = 1
    long_take.present_flow(1.0,long_state,2.2)
    long_take._project_stream(long_take.size.x*.33)
    check(bool(long_take.stream_passes[0].get("ever_visible",false)) and
        long_take.stream_passes.size()==4,
        "the first measure has entered but remaining measures are unexposed")
    long_state["paused"] = true
    long_state["phase"] = "paused"
    long_take.present_flow(1.1,long_state,2.2)
    long_take.trim_resume_speculation(1.2,2.2)
    check(long_take.stream_passes.size()==1 and
        is_equal_approx(float(long_take.stream_passes[0]["world_origin"]),
            original_long_origin),
        "Resume retains only the immutable visible measure, not 3 unseen measures")
    var early_continue: Dictionary = long_take.arm_stream_take(
        1.2,2.2,NAN,true)
    check(not early_continue.is_empty() and
        float(early_continue.get("start_world",INF)) <
            original_long_origin+16.0,
        "continued score starts before the obsolete full-passage endpoint")
    long_take.free()
    # Regression for real Pause -> Resume -> immediate Retry. The old code
    # treated Restart like Resume and reused its already armed source,
    # giving the new graded attempt a deadline in the past.
    var quick := InstrumentedView.new()
    quick.size = Vector2(800,440)
    quick.native_ready = true
    quick.timeline.duration_beats = 8.0
    quick.timeline.measures = [{"start_beat":0.0,"end_beat":4.0},
        {"start_beat":4.0,"end_beat":8.0}]
    quick.timeline.pixels_per_beat = 96.0
    quick.present_flow(0.0,{
        "running":false,"paused":false,"phase":"ready","mode":"practice",
        "piece_fingerprint":"quick","revision":1,"transport_id":0,
        "play_from_beat":0.0},0.0)
    var quick_first: Dictionary = quick.arm_stream_take(0.0,0.0)
    var quick_first_world: float = float(quick_first.get("start_world",NAN))
    check(not quick_first.is_empty(),"quick Play reserves the first take")
    # Simulate Resume's outstanding armed position before a frame consumes
    # the new transport snapshot. Explicit Retry must not steal it.
    var quick_count: int = quick.admissions.size()
    var quick_retry: Dictionary = quick.arm_stream_take(.15,0.0,NAN,false,true)
    check(quick.admissions.size()==quick_count+1 and
        float(quick_retry.get("start_world",-INF)) > quick_first_world+8.0,
        "rapid Retry requires a distinct future reservation")
    check(is_equal_approx(float(quick.stream_passes[0]["world_origin"]),
        quick_first_world),
        "rapid Retry never moves the previous attempt on the staff")
    check(quick.cancel_stream_arm() and quick.stream_passes.size()==2 and
        quick.stream_passes.all(func(item: Dictionary) -> bool:
            return int(item.get("take_owner",-1))==1),
        "failed rapid Retry removes all new strips while retaining original take")
    quick.free()
    # An internal identity collision must roll back admission itself, even
    # before any request can be sent. Otherwise hidden source/rest clips
    # remain in occupied_end and progressively push every attempt rightward.
    var collision := InstrumentedView.new()
    collision.size = Vector2(800,440)
    collision.native_ready = true
    collision.timeline.duration_beats = 8.0
    collision.timeline.measures = [
        {"start_beat":0.0,"end_beat":4.0},
        {"start_beat":4.0,"end_beat":8.0}]
    collision.timeline.pixels_per_beat = 96.0
    collision.present_flow(0.0,{
        "running":false,"paused":false,"phase":"ready","mode":"practice",
        "piece_fingerprint":"collision","revision":1,"transport_id":0,
        "play_from_beat":0.0},0.0)
    collision._stream_queue.online[0]["take_key"] = "armed:%d" % (
        collision._stream_serial+1)
    collision._stream_queue.online[0]["pending"] = false
    var collided: Dictionary = collision.arm_stream_take(.2,0.0)
    var collision_valid := (
        collided.is_empty() and collision.stream_passes.size()==2 and
        collision.stream_passes.all(func(item: Dictionary) -> bool:
            return int(item.get("take_owner",-1))==1) and
        collision._stream_live_serial == -1)
    check(collision_valid,
        "failed owner uniqueness must remove newly inserted future ink %s" % [
            JSON.stringify({"result":collided,"size":collision.stream_passes.size(),
                "serial":collision._stream_serial,
                "live":collision._stream_live_serial,
                "sources":collision.stream_passes.map(
                    func(e): return {"serial":e["serial"],
                        "key":e["take_key"],"pending":e["pending"]})})])
    collision.free()
    # The backend's absolute retry deadline chooses the new future owner.
    # An already-prepared successor for beat zero is not reused for a
    # recovery at beat two, and no earlier online ink is repositioned.
    var recovery := InstrumentedView.new()
    recovery.size = Vector2(800,440)
    recovery.native_ready = true
    recovery.timeline.duration_beats = 8.0
    recovery.timeline.measures = [
        {"start_beat":0.0,"end_beat":4.0},
        {"start_beat":4.0,"end_beat":8.0}]
    recovery.timeline.pixels_per_beat = 96.0
    recovery.present_flow(0.0,{
        "running":false,"paused":false,"phase":"ready",
        "mode":"practice","piece_fingerprint":"recovery",
        "revision":1,"transport_id":0,"play_from_beat":0.0},0.0)
    var first_origin: float = float(recovery.stream_passes[0]["world_origin"])
    var first_owner: int = int(recovery.stream_passes[0]["serial"])
    check(not recovery.arm_stream_take(0.0,0.0).is_empty() and
        recovery.acknowledge_stream_arm(),
        "recovery fixture has one acknowledged immutable first passage")
    recovery._stream_add_take(0.0,40.0,0.0,"autopending")
    var old_future: int = recovery._stream_serial
    check(recovery.enqueue_recovery_queue(4.0,2.0,65.0),
        "recovery engine can replace unexposed future ink at its deadline")
    var new_future: int = recovery._stream_serial
    var score_recovery: Dictionary = {}
    for item in recovery.stream_passes:
        if int(item.get("take_owner",-1)) == recovery._stream_last_admitted and \
                absf(float(item.get("source_floor",-1))-2.0)<.00001:
            score_recovery = item
    check(new_future>old_future and not score_recovery.is_empty() and
        is_equal_approx(
            float(score_recovery["world_origin"])+
            float(score_recovery["source_floor"]),65.0) and
        is_equal_approx(float(score_recovery["source_floor"]),2.0),
        "new retry begins at exact graded downbeat and correct source opening")
    check(is_equal_approx(
        float(recovery.stream_passes[0]["world_origin"]),first_origin) and
        int(recovery.stream_passes[0]["serial"])==first_owner,
        "failure cannot move or replace the already acknowledged prefix")
    var preserved := false
    for event in recovery._stream_queue.history:
        if int(event.get("owner_serial",-1)) == old_future and \
                str(event.get("event",""))=="withdrawn":
            preserved = true
    check(preserved,"withdrawn future score remains in the journal even after reuse")
    check(recovery.enqueue_recovery_queue(4.0,2.0,65.0) and
        recovery._stream_serial==new_future,
        "repeated recovery snapshots cannot duplicate a scheduled passage")
    recovery.free()
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
        check(idle.stream_passes.size()==2 and \
            int(idle.stream_passes[0]["take_owner"]) ==
            int(idle.stream_passes[1]["take_owner"]) and \
            is_equal_approx(float(idle.stream_passes[0]["clip_ceiling"]),
                float(idle.stream_passes[1]["clip_floor"])),
            "READY keeps one logical take as adjoining immutable measure strips")
        # The offline FIFO is a work queue: a withdrawn READY source may
        # be immediately consumed by the next immutable enqueue. The
        # append-only journal, however, must preserve every withdrawal.
        check(idle._stream_queue.history.size() >= idle.admissions.size(),
            "READY replacements are all represented in the event journal")
        check(idle.drawn_noteheads.is_empty(),
            "READY must not display idle noteheads without Play")
        var reserve: Dictionary = idle.stream_passes[0]
        var threshold: float = idle_world+idle._stream_right_beats()+ \
            idle._stream_header_beats(0.0)
        check(float(reserve["world_origin"]) > threshold,
            "READY replaces offscreen source rather than shifting an existing origin")
    var recorded_withdrawals := 0
    for event in idle._stream_queue.history:
        if str(event.get("event","")) == "withdrawn":
            recorded_withdrawals += 1
    check(recorded_withdrawals > 0 and
        idle._stream_queue.history.size() >= idle.admissions.size() +
            recorded_withdrawals,
        "all displaced READY source plans remain recoverable from the journal")
    var idle_armed: Dictionary = idle.arm_stream_take(idle.stream_world_beat,0)
    var idle_before_play: int = idle.admissions.size()
    check(not idle_armed.is_empty() and
        idle.admissions.size()==idle_before_play and
        idle.stream_passes.size()==2 and \
        idle.stream_passes.all(func(item: Dictionary) -> bool:
            return bool(item.get("armed",false))),
        "Play claims every strip of the READY take without adding ink")
    var idle_origin: float = float(idle.stream_passes[0]["world_origin"])
    check(idle.cancel_stream_arm() and
        str(idle.stream_passes[0].get("take_key",""))=="prepared" and
        bool(idle.stream_passes[0].get("pending",false)) and
        bool(idle.stream_passes[0].get("hidden_until_armed",false)),
        "failed Play restores its original silent READY owner atomically")
    idle.present_flow(idle.stream_world_beat+.1,ready_state,0.0)
    idle.drawn_note_instances.clear()
    idle.drawn_noteheads.clear()
    idle._project_stream(idle.size.x*.33)
    check(idle.stream_passes.size()==2 and idle.drawn_noteheads.is_empty() and
        is_equal_approx(float(idle.stream_passes[0]["world_origin"]),idle_origin) and \
        idle.stream_passes.all(func(item: Dictionary) -> bool:
            return bool(item.get("pending",false)) and \
                bool(item.get("hidden_until_armed",false)) and \
                not bool(item.get("armed",false))),
        "failed Play restores all immutable READY strips without ghost notes")
    idle.free()
    print("STREAM_PROJECTED_OVERLAP_FAILURES:",failures)
    quit(0 if failures==0 else 1)
