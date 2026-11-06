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
class PeerOwner:
    extends Owner
    var _stream_queue
    var timeline := {"pixels_per_beat":100.0,"duration_beats":4.0}
    func staff_gap() -> float:
        return 20.0

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
    var restored_ok: bool = restored.bind_score(score_key,folder,true)
    var same_plan: bool = (restored.offline.size() == 1 and
        JSON.stringify(restored.offline[0]["plan"]) ==
        JSON.stringify(queue.offline[0]["plan"]))
    check(restored_ok and restored.online.is_empty() and same_plan,
        "offline FIFO survives reopening: loaded=%s ready=%d history=%d error=%s" %
        [str(restored_ok),restored.offline.size(),restored.history.size(),
            restored.last_error])
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
    check(after_close.bind_score(score_key,folder,true) and
        after_close.offline.size()==1,
        "even score teardown cannot lose the last musical source")
    var wrong_source := Queue.new()
    check(wrong_source.bind_score(score_key+"-different",folder,true) and
        wrong_source.offline.is_empty(),
        "a different musical score cannot consume another song's offline ink")
    var bad: Array = passage(5,60.0,"prepared",true)
    bad[1]["world_origin"] = 61.0
    check(not after_close.enqueue(other_owner,bad,
        new_source_pool,new_rest_pool,null,
        23.0,800.0,playhead,density,gap,4.0),
        "a rest cannot independently choose its world-time coordinate")
    # An archived source with the same source window but a DIFFERENT
    # passage length must not be substituted for the requested material.
    # Both the printed rest and the backend grading deadline use the new
    # duration, not the archived one's earlier endpoint.
    var changed_duration: Array = passage(6,70.0,"prepared",true)
    changed_duration[0]["piece_duration"] = 4.5
    changed_duration[1]["world_origin"] = 74.5
    var archived_before: int = after_close.offline.size()
    check(after_close.enqueue(other_owner,changed_duration,
        new_source_pool,new_rest_pool,null,
        23.0,800.0,playhead,density,gap,4.0) and
        after_close.offline.size() == archived_before and
        int(after_close.history[-1]["from_id"]) == 0 and
        is_equal_approx(float(after_close.online[0]["piece_duration"]),4.5) and
        is_equal_approx(float(after_close.online[1]["world_origin"]),74.5),
        "offline reuse rejects same-window passages with different durations")
    var impossible_span: Array = passage(7,90.0,"prepared",true)
    impossible_span[0]["piece_duration"] = 3.0
    impossible_span[1]["world_origin"] = 93.0
    check(not after_close.enqueue(other_owner,impossible_span,
        new_source_pool,new_rest_pool,null,
        23.0,800.0,playhead,density,gap,4.0),
        "source ink cannot extend beyond the declared passage duration")
    # Interrupted sessions leave enqueued-but-never-finalized material in
    # the checked journal. A new process recovers it as offline source data,
    # with NO attempt to reuse the obsolete old screen coordinates.
    var interrupted_key: String = score_key+"-interrupted"
    var interrupted_writer := Queue.new()
    check(interrupted_writer.bind_score(interrupted_key,folder),
        "interrupted-score journal is initialized")
    var interrupted_owner := Owner.new()
    root.add_child(interrupted_owner)
    interrupted_owner.size = owner.size
    check(interrupted_writer.enqueue(interrupted_owner,
        passage(1,11.0,"prepared",true),
        [],[],null,0.0,800.0,playhead,density,gap,4.0),
        "interrupted session journals its online source before exposure")
    var interrupted_reader := Queue.new()
    check(interrupted_reader.bind_score(interrupted_key,folder,true) and
        interrupted_reader.offline.size()==1 and
        str(interrupted_reader.offline[0]["event"])=="interrupted",
        "unclosed online source is recovered as offline material on restart")
    check(interrupted_reader.enqueue(other_owner,
        passage(2,56.0,"prepared",true),[],[],null,
        23.0,800.0,playhead,density,gap,4.0) and
        interrupted_reader.offline.is_empty(),
        "recovered interrupted source is reinserted at a NEW offscreen location")
    # After a SECOND crash/restart the old interrupted owner must NOT
    # return alongside its already-consumed successor. Each replay is a
    # one-time transfer of offline ownership, not a clone of the passage.
    var interrupted_again := Queue.new()
    check(interrupted_again.bind_score(interrupted_key,folder,true) and
        interrupted_again.offline.size()==1 and
        int(interrupted_again.offline[0]["id"]) ==
            int(interrupted_reader.history[-1]["id"]),
        "second restart must recover only the active successor, never the consumed predecessor")
    check(interrupted_again.enqueue(other_owner,
        passage(3,70.0,"prepared",true),[],[],null,
        23.0,800.0,playhead,density,gap,4.0) and
        interrupted_again.offline.is_empty(),
        "second replay consumes interrupted successor exactly once")
    var interrupted_third := Queue.new()
    check(interrupted_third.bind_score(interrupted_key,folder,true) and
        interrupted_third.offline.size()==1 and
        int(interrupted_third.offline[0]["id"]) ==
            int(interrupted_again.history[-1]["id"]),
        "third restart never resurrects either previously consumed owner")
    # A fully finished source with a remaining written rest must archive
    # its complete ORIGINAL passage on unload, never an orphan rest alone.
    var trailing_key: String = score_key+"-rest"
    var trailing_writer := Queue.new()
    check(trailing_writer.bind_score(trailing_key,folder) and
        trailing_writer.enqueue(other_owner,
            passage(1,10.0,"prepared",true),[],[],null,
            0.0,800.0,playhead,density,gap,4.0) and
        trailing_writer.enqueue(other_owner,
            passage(2,23.0,"prepared",true),[],[],null,
            0.0,800.0,playhead,density,gap,4.0),
        "rest-only teardown fixture admits two complete source/rest owners")
    var source_departed: Array[int] = trailing_writer.expire_front(
        other_owner,19.0,density,gap,4.0,playhead)
    check(source_departed == [1] and
        trailing_writer.online.size()==3 and
        trailing_writer.online[0]["kind"]=="rest" and
        int(trailing_writer.online[1]["owner_serial"])==2,
        "source departs while its written rest and a later owner remain")
    trailing_writer.reset(other_owner)
    check(trailing_writer.online.is_empty() and
        trailing_writer.offline.size()==2 and
        trailing_writer.offline[0]["plan"].size()==2 and
        trailing_writer.offline[1]["plan"].size()==2 and
        int(trailing_writer.offline[1]["owner_serial"])==2,
        "closing trailing-rest owner also preserves the NEXT complete owner without over-popping")
    var rest_reader := Queue.new()
    check(rest_reader.bind_score(trailing_key,folder,true) and
        rest_reader.offline.size()==2 and
        rest_reader.offline[0]["plan"].size()==2 and
        rest_reader.offline[1]["plan"].size()==2,
        "both trailing-rest and next-source passages survive reopening")
    # Two overlapping lesson renderers with identical musical source
    # MUST share the same journal sequence rather than creating duplicate
    # IDs and losing one of their source plans on restart.
    var shared_key: String = score_key+"-overlapping"
    var first_layer := Queue.new()
    var second_layer := Queue.new()
    check(first_layer.bind_score(shared_key,folder) and
        second_layer.bind_score(shared_key,folder) and
        first_layer._archive == second_layer._archive,
        "concurrent renderer layers use one writer for identical score source")
    check(first_layer.enqueue(owner,passage(1,10.0,"prepared",true),
        [],[],null,0.0,800.0,playhead,density,gap,4.0) and
        second_layer.enqueue(other_owner,passage(1,23.0,"prepared",true),
        [],[],null,0.0,800.0,playhead,density,gap,4.0),
        "independent render layers append both source plans through shared journal")
    check(first_layer.history.size()==2 and
        int(first_layer.history[0]["id"]) != int(first_layer.history[1]["id"]) and
        first_layer.history[0]["owner_serial"] == 1 and
        first_layer.history[1]["owner_serial"] == 1 and
        first_layer.history[0]["writer_id"] != first_layer.history[1]["writer_id"],
        "two renderers may both own serial 1 without colliding in journal identity")
    var cold_layer := Queue.new()
    check(cold_layer.bind_score(shared_key,folder,true) and
        cold_layer.offline.size()==2 and
        cold_layer.offline[0]["plan"].size()==2 and
        cold_layer.offline[1]["plan"].size()==2,
        "both independently queued overlapping source plans survive a cold restart")
    # Measure strips are independently immutable. After the first
    # source strip enters the viewport, all unseen successors (including
    # a semantic rest) must still be withdrawn from the RIGHT.
    var strip_owner := Owner.new()
    root.add_child(strip_owner)
    strip_owner.size = owner.size
    var strip_queue := Queue.new()
    check(strip_queue.bind_score(score_key+"-strip",folder),
        "source-strip journal is initialized")
    var first_strip: Array = [{
        "kind":"source","owner_serial":1,"take_owner":1,
        "world_origin":14.0,"source_floor":0.0,"source_ceiling":4.0,
        "clip_floor":-2.0,"clip_ceiling":4.0,
        "piece_duration":8.0,"take_key":"prepared","pending":true}]
    var next_strip: Array = [{
        "kind":"source","owner_serial":2,"take_owner":1,
        "world_origin":14.0,"source_floor":4.0,"source_ceiling":8.0,
        "clip_floor":4.0,"clip_ceiling":8.2,
        "piece_duration":8.0,"take_key":"prepared","pending":true},
        {"kind":"rest","owner_serial":2,"take_owner":1,
        "world_origin":22.0,"source_floor":0.0,
        "source_ceiling":4.0,"take_key":"rest"}]
    check(strip_queue.enqueue(strip_owner,first_strip,[],[],null,
        0.0,800.0,playhead,density,gap,8.0) and
        strip_queue.enqueue(strip_owner,next_strip,[],[],null,
        0.0,800.0,playhead,density,gap,8.0) and
        strip_queue.online.size()==3,
        "source strips are contiguous, ordered and admitted as one take")
    check(Lifecycle.activate(strip_queue.online,1,"engine-transport",false) and
        str(strip_queue.online[1]["take_key"])=="engine-transport",
        "engine transport binds both source strips without changing geometry")
    Lifecycle.project(strip_queue.online[0],11.0,playhead,density,gap,
        strip_owner.size,8.0)
    check(bool(strip_queue.online[0].get("ever_visible",false)) and
        not bool(strip_queue.online[1].get("ever_visible",false)),
        "the first measure locks while the future measure remains unseen")
    var strip_removed: Array[int] = strip_queue.withdraw_tail(
        strip_owner,11.0,density,gap,8.0,800.0,playhead,"failed_lesson")
    check(strip_removed.has(2) and strip_removed.has(-2) and
        strip_queue.online.size()==1 and
        is_equal_approx(float(strip_queue.online[0]["world_origin"]),14.0) and
        strip_queue.offline.size()==1,
        "failed lesson preserves visible measure and archives maximal invisible suffix")
    strip_queue.reset(strip_owner)

    # A newly promoted lesson must check all still-live preceding layers.
    var peer := PeerOwner.new()
    root.add_child(peer)
    peer.size = owner.size
    peer._stream_queue = Queue.new()
    check(peer._stream_queue.bind_score(score_key+"-peer",folder) and
        peer._stream_queue.enqueue(peer,passage(1,10.0,"prepared",true),
        [],[],null,0.0,800.0,playhead,density,gap,4.0),
        "an outgoing renderer owns future ink before lesson transition")
    var incoming := Queue.new()
    check(incoming.bind_score(score_key+"-incoming",folder),
        "new renderer has a distinct source archive")
    incoming.register_peer(peer)
    check(not incoming.enqueue(strip_owner,passage(1,15.0,"prepared",true),
        [],[],null,0.0,800.0,playhead,density,gap,4.0),
        "new lesson cannot overlap older renderer's moving notes and rest")
    check(incoming.enqueue(strip_owner,passage(1,24.0,"prepared",true),
        [],[],null,0.0,800.0,playhead,density,gap,4.0),
        "new lesson can append immediately after all older ink")
    var peer_bound: float = incoming.minimum_peer_opening(
        density,800.0,playhead)
    check(peer_bound >= 18.0-.00001,
        "READY derives the chronological predecessor boundary once")
    var fast_density_queue := Queue.new()
    check(fast_density_queue.bind_score(score_key+"-mixed-density",folder),
        "mixed-density renderer journal is initialized")
    fast_density_queue.register_peer(peer)
    check(not fast_density_queue.enqueue(strip_owner,
        passage(1,24.0,"prepared",true),[],[],null,
        0.0,800.0,playhead,160.0,gap,4.0) and
        fast_density_queue.enqueue(strip_owner,
        passage(1,30.0,"prepared",true),[],[],null,
        0.0,800.0,playhead,160.0,gap,4.0),
        "different score densities require screen-space exit clearance")
    fast_density_queue.reset(strip_owner)
    incoming.reset(strip_owner)
    peer._stream_queue.reset(peer)
    peer.queue_free()
    strip_owner.queue_free()
    interrupted_owner.queue_free()
    owner.queue_free()
    other_owner.queue_free()
    var absolute: String = ProjectSettings.globalize_path(folder)
    for key in [score_key,interrupted_key,trailing_key,shared_key]:
        DirAccess.remove_absolute(absolute.path_join(key.sha256_text()+".jsonl"))
    DirAccess.remove_absolute(absolute)
    print("STREAM_SCORE_QUEUE_FAILURES:",failures)
    quit(0 if failures==0 else 1)
