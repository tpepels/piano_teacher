extends SceneTree
## Real source/rest CanvasItems + persistent offline passage FIFO. This
## exercises the exact architecture used by the production renderer.
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
    var score_key: String = "fifo-source-%d" % Time.get_ticks_usec()
    var folder: String = "user://queue-acceptance-%d" % Time.get_ticks_usec()
    check(queue.bind_score(score_key,folder),
        "source identity establishes a durable offline queue")
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
    check(queue.online.size()==4 and queue.offline.is_empty() and
        queue.history.size()==2,
        "online material is journaled but NOT duplicated in offline FIFO")
    var original: Array = queue.history[0]["plan"].duplicate(true)
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
    check(queue.offline.size()==1 and
        queue.offline[0]["event"]=="withdrawn" and
        queue.offline[0]["owner_serial"]==2,
        "withdrawn B enters the separate offline FIFO as complete source/rest")
    var withdrawn_copy: Array = queue.offline[0]["plan"].duplicate(true)
    var withdrawn_id: int = int(queue.offline[0]["id"])
    check(queue.withdraw_tail(owner,8.0,density,gap,4.0,
        800.0,playhead,"second_failure").is_empty(),
        "nothing in the visible prefix can be withdrawn")
    check(queue.online[0]["world_origin"]==10.0 and
        queue.online[0]["source_ceiling"]==4.0 and
        queue.history[0]["plan"]==original,
        "visible score and original journaled content stay immutable")
    var removed: Array[int] = queue.expire_front(owner,19.0,
        density,gap,4.0,playhead)
    check(removed==[1] and queue.online.size()==1 and
        queue.online[0]["kind"]=="rest",
        "source retires from head after printed ink; its rest remains")
    removed = queue.expire_front(owner,23.0,
        density,gap,4.0,playhead)
    check(removed==[-1] and queue.online.is_empty(),
        "paired rest exits strictly from the queue front")
    # No caller builds a manual second queue. Enqueue automatically claims
    # matching offline source ink and assigns a NEW immutable world origin.
    check(queue.enqueue(owner,passage(3,33.0,"prepared",true),
        source_pool,rest_pool,null,23.0,800.0,playhead,density,gap,4.0),
        "an existing offline source is automatically re-enqueued")
    check(queue.online.size()==2 and queue.offline.is_empty() and
        queue.online[0]["owner_serial"]==3 and
        queue.online[0]["world_origin"]==33.0 and
        queue.online[1]["world_origin"]==37.0,
        "replayed passage gets one new owner and one new source/rest position")
    check(queue.history[-1]["from_id"]==withdrawn_id and
        queue.history[-1]["reason"]=="offline_reuse" and
        queue.history[2]["plan"]==withdrawn_copy,
        "replay consumes exactly one offline owner without modifying history")
    var canceled: Array[int] = queue.withdraw_tail(owner,23.0,
        density,gap,4.0,800.0,playhead,"canceled_request")
    check(canceled.has(3) and canceled.has(-3) and
        queue.offline.size()==1 and queue.online.is_empty(),
        "canceled source/rest returns together to offline queue")
    # Reload the score journal through an entirely different Queue object,
    # simulating reopening the song in a new renderer/process.
    var restored := Queue.new()
    check(restored.bind_score(score_key,folder) and
        restored.online.is_empty() and restored.offline.size()==1 and
        restored.offline[0]["plan"]==queue.offline[0]["plan"],
        "offline FIFO survives a fresh queue instance with identical content")
    var other_owner := Owner.new()
    root.add_child(other_owner)
    other_owner.size = owner.size
    var new_source_pool: Array = []
    var new_rest_pool: Array = []
    check(restored.enqueue(other_owner,passage(4,44.0,"prepared",true),
        new_source_pool,new_rest_pool,null,23.0,
        800.0,playhead,density,gap,4.0) and
        restored.offline.is_empty() and restored.online.size()==2,
        "restored offline passage is actually reusable after reopening")
    # The append-only event includes both the new owner and the ID of the
    # consumed offline owner; no crash can separate the two mutations.
    check(restored.history[-1]["from_id"]==
        int(queue.offline[0]["id"]),
        "reopen/replay commits as one journaled operation")
    restored.reset(other_owner)
    check(restored.offline.size()==1 and restored.online.is_empty(),
        "score close returns its final source to the persistent offline FIFO")
    var after_close := Queue.new()
    check(after_close.bind_score(score_key,folder) and
        after_close.offline.size()==1,
        "even score teardown cannot lose the last musical source")
    var wrong_source := Queue.new()
    check(wrong_source.bind_score(score_key+"-different",folder) and
        wrong_source.offline.is_empty(),
        "a different musical score cannot consume another song's offline ink")
    var bad: Array = passage(5,60.0,"prepared",true)
    bad[1]["world_origin"] = 61.0
    check(not after_close.enqueue(other_owner,bad,
        new_source_pool,new_rest_pool,null,
        23.0,800.0,playhead,density,gap,4.0),
        "a rest cannot independently choose its world-time coordinate")
    owner.queue_free()
    other_owner.queue_free()
    var absolute: String = ProjectSettings.globalize_path(folder)
    DirAccess.remove_absolute(absolute.path_join(score_key.sha256_text()+".jsonl"))
    DirAccess.remove_absolute(absolute)
    print("STREAM_SCORE_QUEUE_FAILURES:",failures)
    quit(0 if failures==0 else 1)
