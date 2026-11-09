extends SceneTree
## Actual NativeView / immutable FIFO / transport preflight regression. No
## mocked queue or fabricated world positions are used by the admission path.
const NativeView := preload("res://notation/native/view.gd")
const Reservation := preload("res://score_transport_reservation.gd")
var failures := 0

class CompiledSegment:
    extends Node2D
    var compiled := true
    var note_instances: Array = []
    # Retained-strip interface: binds the strip's take to the status ledger.
    var synced_take := ""
    func sync_note_status(take_key: String, _source, _visible_ink: bool) -> void:
        synced_take = take_key

class View:
    extends "res://notation/native/view.gd"
    func retained_ready() -> bool:
        return true
    func _new_retained_segment(_kind: String):
        var segment := CompiledSegment.new()
        add_child(segment)
        retained_all_segments.append(segment)
        return segment

func check(ok: bool, why: String) -> void:
    if not ok:
        failures += 1
        print("TRANSPORT_RESERVATION_FAILED:",why)

func _initialize() -> void:
    call_deferred("_run")

func _run() -> void:
    var v := View.new()
    v.size = Vector2(800,440)
    v.native_ready = true
    v.timeline.duration_beats = 16.0
    v.timeline.pixels_per_beat = 96.0
    v.timeline.measures = [
        {"start_beat":0.0,"end_beat":4.0},
        {"start_beat":4.0,"end_beat":8.0},
        {"start_beat":8.0,"end_beat":12.0},
        {"start_beat":12.0,"end_beat":16.0}]
    var state: Dictionary = {"running":false,"paused":false,
        "phase":"ready","mode":"practice","revision":1,
        "piece_fingerprint":"preflight","transport_id":0,
        "play_from_beat":0.0}
    v.present_flow(0.0,state,0.0)
    var original_count: int = v.stream_passes.size()
    check(original_count == 4,"READY has one immutable four-measure take")
    var original_origin: float = float(v.stream_passes[0]["world_origin"])
    # Owner decision 2026-11-08 ("the notes should appear closer to the
    # playhead, so the wait is about one bar"): on an empty strip Play opens
    # one count-in bar ahead of the playhead. The never-seen READY take is
    # withdrawn instead of being reused from beyond the right edge.
    const COUNT_IN := 4.0
    var start_plan: Dictionary = Reservation.plan(v,"start",0.01,0.0,COUNT_IN)
    check(bool(start_plan.get("ok",false)) and
        str(start_plan.get("mode",""))=="append" and
        bool(start_plan.get("empty_strip",false)) and
        is_equal_approx(float(start_plan.get("start_world",NAN)),0.01+COUNT_IN),
        "Play on an empty strip plans its first beat one count-in bar ahead: " +
            str(start_plan))
    check(v.stream_passes.size()==original_count and
        float(v.stream_passes[0]["world_origin"])==original_origin,
        "preflight must never mutate the queue")
    var started: Dictionary = v.reserve_transport_action("start",0.01,0.0,COUNT_IN)
    check(not started.is_empty() and v.stream_passes.size()==original_count and
        is_equal_approx(float(started.get("start_world",NAN)),0.01+COUNT_IN),
        "Play replaces the unseen READY take with one take at the count-in bar")
    check(float(started.get("start_world",NAN)) < original_origin,
        "the opening no longer waits behind the offscreen READY slot")
    original_origin = float(v.stream_passes[0]["world_origin"])
    v._project_stream(v.size.x*.33)
    check(bool(v.stream_passes[0].get("ever_visible",false)),
        "the opening is on the empty staff as soon as Play is armed")
    check(v.acknowledge_stream_arm(),"Play backend acknowledgment binds take")
    state["running"] = true
    state["phase"] = "playing"
    state["transport_id"] = 1
    v.present_flow(0.02,state,0.0)
    var entry_world: float = maxf(0.03,original_origin -
        v._stream_header_beats(0.0)-v._stream_right_beats()+0.22)
    v.present_flow(entry_world,state,3.25)
    v._project_stream(v.size.x*.33)
    check(bool(v.stream_passes[0].get("ever_visible",false)),
        "first measure is physically exposed before Pause")
    state["paused"] = true
    state["phase"] = "paused"
    v.present_flow(entry_world+.02,state,3.25)
    # Pause now withdraws the never-exposed suffix of the ACTIVE attempt,
    # not just unrelated automatic copies. Preserve the one visible prefix.
    var paused_count: int = v.stream_passes.size()
    check(paused_count >= 1 and paused_count < original_count,
        "Pause retracts unseen later measures while retaining visible ink")
    var resume_world: float = entry_world+.03
    var resume_plan: Dictionary = Reservation.plan(
        v,"resume",resume_world,3.25,COUNT_IN)
    check(bool(resume_plan.get("ok",false)) and
        str(resume_plan.get("mode",""))=="append" and
        int(resume_plan.get("remaining_count",-1))==1,
        "Resume preflight withdraws only unseen future measure strips")
    check(v.stream_passes.size()==paused_count and
        is_equal_approx(float(v.stream_passes[0]["world_origin"]),
            original_origin),
        "Resume preflight leaves the paused online queue untouched")
    check(not bool(resume_plan.get("empty_strip",true)),
        "with the paused take still ahead of the playhead Resume stays append-only")
    var resumed: Dictionary = v.reserve_transport_action(
        "resume",resume_world,3.25,COUNT_IN)
    check(not resumed.is_empty() and
        is_equal_approx(float(v.stream_passes[0]["world_origin"]),
            original_origin),
        "Resume commits a new future owner without altering visible ink")
    check(float(resumed.get("start_world",INF)) < original_origin+16.0,
        "Resume does not wait for the entire obsolete passage")
    check(float(resumed.get("start_world",-INF)) > resume_world,
        "new grading deadline remains strictly in the future")
    var pre_invalid: int = v.stream_passes.size()
    var invalid: Dictionary = Reservation.plan(v,"restart",resume_world,25.0,COUNT_IN)
    check(not bool(invalid.get("ok",true)) and
        v.stream_passes.size()==pre_invalid,
        "invalid source is rejected without a queue mutation")
    v.free()
    print("TRANSPORT_RESERVATION_FAILURES:",failures)
    quit(0 if failures==0 else 1)
