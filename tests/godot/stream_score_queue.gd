extends SceneTree
## True online/offline score FIFO: real CanvasItem windows, source/rest pairs,
## irrevocable visible prefix, maximal safe tail withdrawal and strict
## left-only expiration. Failed/unused passages stay reproducible offline.
const Queue := preload("res://score_stream_queue.gd")
const Lifecycle := preload("res://notation/native/stream_lifecycle.gd")

class FakeSegment:
    extends Node2D
    var compiled := true
    var note_instances: Array = []
class Owner:
    extends Control
    func _new_retained_segment(_kind: String):
        var part := FakeSegment.new()
        add_child(part)
        return part

var failures := 0
func check(ok: bool, why: String) -> void:
    if not ok:
        failures += 1
        print("STREAM_SCORE_QUEUE_FAILED:",why)
func _initialize() -> void:
    call_deferred("_run")

func passage(owner_id: int, origin: float, take: String,
        pending: bool) -> Array:
    return [
        {"kind":"source","owner_serial":owner_id,
            "world_origin":origin,"source_floor":0.0,
            "source_ceiling":4.0,"piece_duration":4.0,
            "take_key":take,"pending":pending,
            "hidden_until_armed":pending and take=="prepared"},
        {"kind":"rest","owner_serial":owner_id,
            "world_origin":origin+4.0,"source_floor":0.0,
            "source_ceiling":4.0,"take_key":"rest","pending":false,
            "hidden_until_armed":pending and take=="prepared"}
    ]

func _run() -> void:
    var owner := Owner.new()
    root.add_child(owner)
    owner.size = Vector2(800,420)
    var queue := Queue.new()
    var source_pool: Array = []
    var rest_pool: Array = []
    var density := 100.0
    var gap := 20.0
    var playhead := 264.0
    check(queue.enqueue(owner,passage(1,10.0,"prepared",true),
        source_pool,rest_pool,null,0.0,800.0,playhead,density,gap,4.0),
        "first passage enters only beyond right-hand viewport")
    check(queue.enqueue(owner,passage(2,23.0,"autopending",true),
        source_pool,rest_pool,null,0.0,800.0,playhead,density,gap,4.0),
        "second source/rest pair appends beyond its predecessor")
    check(queue.online.size()==4 and queue.offline.size()==2,
        "exactly two online source/rest owners have preserved offline plans")
    var original: Array = queue.offline[0]["plan"].duplicate(true)
    check(not queue.enqueue(owner,passage(2,41.0,"prepared",true),
        source_pool,rest_pool,null,0.0,800.0,playhead,density,gap,4.0) and
        queue.online.size()==4,
        "duplicate owner cannot create another online source/rest pair")
    check(not queue.enqueue(owner,passage(3,16.0,"prepared",true),
        source_pool,rest_pool,null,0.0,800.0,playhead,density,gap,4.0),
        "an insertion between online passages violates FIFO ordering")
    check(Lifecycle.activate(queue.online,1,"acknowledged",false),
        "authoritative backend transport binds first passage")
    for item in queue.online:
        if int(item["owner_serial"]) == 1:
            Lifecycle.project(item,8.0,playhead,density,gap,
                owner.size,4.0)
    check(queue.exposed_owner(1),"first source has physically entered the view")
    var withdrawn: Array[int] = queue.withdraw_tail(
        owner,8.0,density,gap,4.0,800.0,playhead,"failure")
    check(withdrawn.has(2) and withdrawn.has(-2) and
        queue.online.size()==2 and queue.exposed_owner(1),
        "failure withdraws exactly the unexposed suffix, retaining visible A")
    check(queue.offline.size()==3 and
        queue.offline[-1]["event"]=="withdrawn" and
        queue.offline[-1]["owner_serial"]==2,
        "withdrawn B is retained as an offline immutable plan")
    check(queue.withdraw_tail(owner,8.0,density,gap,4.0,
        800.0,playhead,"second_failure").is_empty(),
        "nothing in the visible prefix can be withdrawn")
    check(queue.online[0]["world_origin"]==10.0 and
        queue.online[0]["source_ceiling"]==4.0 and
        queue.offline[0]["plan"]==original,
        "visible source geometry and original offline plan remain immutable")
    var removed: Array[int] = queue.expire_front(owner,19.0,
        density,gap,4.0,playhead)
    check(removed==[1] and queue.online.size()==1 and
        queue.online[0]["kind"]=="rest",
        "source retires from queue head after last actual ink; rest remains")
    removed = queue.expire_front(owner,23.0,
        density,gap,4.0,playhead)
    check(removed==[-1] and queue.online.is_empty(),
        "paired rest independently exits at the same physical boundary policy")
    # Reuse B's unchanged offline source plan as a newly scheduled owner C,
    # with only a NEW future location, not a change to B's existing entry.
    var offline_plan: Array = queue.offline[2]["plan"].duplicate(true)
    var replay: Array = []
    for spec in offline_plan:
        var fresh: Dictionary = spec.duplicate(true)
        fresh["owner_serial"] = 3
        fresh["world_origin"] = float(spec["world_origin"])+10.0
        fresh["take_key"] = "prepared" if fresh["kind"]=="source" else "rest"
        fresh["pending"] = fresh["kind"]=="source"
        fresh["hidden_until_armed"] = true
        replay.append(fresh)
    check(queue.enqueue(owner,replay,source_pool,rest_pool,null,
        23.0,800.0,playhead,density,gap,4.0),
        "withdrawn offline score can be replayed as new immutable future owner")
    check(queue.online.size()==2 and
        int(queue.online[0]["owner_serial"])==3 and
        int(queue.online[1]["owner_serial"])==3,
        "replayed owner has exactly one source and one rest")
    check(queue.offline[2]["plan"]==offline_plan,
        "replaying offline notation cannot consume or mutate its archive")
    var aborted: Array[int] = queue.withdraw_tail(owner,23.0,
        density,gap,4.0,800.0,playhead,"canceled_request")
    check(aborted.has(3) and aborted.has(-3) and queue.online.is_empty(),
        "canceled pre-commit passage removes its complete rightmost owner")
    var bad: Array = passage(4,42.0,"prepared",true)
    bad[1]["world_origin"] = 43.0
    check(not queue.enqueue(owner,bad,source_pool,rest_pool,null,
        23.0,800.0,playhead,density,gap,4.0),
        "a rest cannot independently select a different world-time origin")
    owner.queue_free()
    print("STREAM_SCORE_QUEUE_FAILURES:",failures)
    quit(0 if failures==0 else 1)
