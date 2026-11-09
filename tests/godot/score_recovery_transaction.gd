extends SceneTree
## Recovery is a single preflight/commit; a late or rejected deadline must
## never destroy music still reserved on the immutable continuous axis.
const Native := preload("res://notation/native/view.gd")

class Segment:
    extends Node2D
    var compiled := true
    var note_instances: Array = []
    func sync_note_status(_key: String, _source, _visible: bool) -> void:
        pass

class View:
    extends "res://notation/native/view.gd"
    var reject_one := false
    func retained_ready() -> bool:
        return true
    func _new_retained_segment(_kind: String):
        var part := Segment.new()
        add_child(part)
        retained_all_segments.append(part)
        return part
    func _stream_add_take(source_beat: float, start_world: float,
            from_beat: float, take_key: String,
            empty_strip: bool = false) -> void:
        if reject_one:
            reject_one = false
            return
        super._stream_add_take(source_beat,start_world,from_beat,
            take_key,empty_strip)

var failures := 0
func check(ok: bool, why: String) -> void:
    if not ok:
        failures += 1
        print("SCORE_RECOVERY_TRANSACTION_FAILED:",why)

func fixture() -> View:
    var view := View.new()
    view.size = Vector2(800,440)
    view.native_ready = true
    view.timeline.duration_beats = 8.0
    view.timeline.pixels_per_beat = 96.0
    view.timeline.measures = [
        {"start_beat":0.0,"end_beat":4.0},
        {"start_beat":4.0,"end_beat":8.0}]
    view.present_flow(0.0,{
        "loaded":true,"phase":"ready","mode":"practice",
        "running":false,"paused":false,"play_from_beat":0.0,
        "revision":1,"transport_id":0,"piece_fingerprint":"txn"
    },0.0)
    return view

func _initialize() -> void:
    call_deferred("_run")

func _run() -> void:
    var v := fixture()
    var original := v.stream_passes.duplicate(true)
    check(original.size() == 2,
        "source begins as two immutable offscreen measures")
    check(not v.enqueue_recovery_queue(0.0,0.0,1.0,"too_early"),
        "impossible deadline is rejected before source withdrawal")
    check(v.stream_passes.size() == original.size() and
        float(v.stream_passes[0]["world_origin"]) ==
            float(original[0]["world_origin"]),
        "failed preflight keeps every original source world position")
    check(v.enqueue_recovery_queue(0.0,0.0,15.0,"accepted"),
        "valid source-deadline transaction replaces hidden future")
    var saved_owner: int = int(v._scheduled_score_plan_ids["accepted"])
    check(v._stream_queue.has_take(saved_owner),
        "accepted plan ID is backed by an actual online source")
    v.trim_future_queue("test_external_replan")
    check(not v._stream_queue.has_take(saved_owner),
        "external withdrawal invalidates the original plan material")
    check(v.enqueue_recovery_queue(0.0,0.0,15.0,"accepted") and
        v._stream_queue.has_take(
            int(v._scheduled_score_plan_ids["accepted"])) and
        int(v._scheduled_score_plan_ids["accepted"]) != saved_owner,
        "same plan ID is admitted again after its notes were withdrawn")
    v.free()

    var broken := fixture()
    var before := broken.stream_passes.duplicate(true)
    broken.reject_one = true
    check(not broken.enqueue_recovery_queue(0.0,0.0,15.0,"failed_commit"),
        "injected allocation failure is not a successful recovery")
    check(broken.stream_passes.size()==before.size() and
        float(broken.stream_passes[0]["world_origin"]) ==
            float(before[0]["world_origin"]) and
        float(broken.stream_passes[-1]["source_ceiling"]) ==
            float(before[-1]["source_ceiling"]),
        "failed append restores the exact previous source/rest suffix")
    broken.free()
    print("SCORE_RECOVERY_TRANSACTION_FAILURES:",failures)
    quit(0 if failures==0 else 1)
