extends RefCounted
const StreamGeometry := preload("res://notation/native/stream_geometry.gd")
## Owns the transport-to-immutable-take binding lifecycle: provisional arm,
## backend acknowledgement, Pause identity and failed-command compensation.
## Physical append/withdraw remains the sole queue owner's transaction.
const Admission := preload("res://score_stream_admission.gd")
const StreamLifecycle := preload("res://notation/native/stream_lifecycle.gd")
var queue
var last_take := ""
var was_paused := false
var paused_owner := -1
var live_serial := -1
var armed_serial := -1
var armed_segment_id := ""
var live_segment_id := ""
var arm_rollback: Dictionary = {}
var arm_acknowledged := false
var unscored_take := ""

func _init(stream_queue) -> void:
    queue = stream_queue

func reset() -> void:
    last_take = ""
    was_paused = false
    paused_owner = -1
    live_serial = -1
    armed_serial = -1
    armed_segment_id = ""
    live_segment_id = ""
    arm_rollback.clear()
    arm_acknowledged = false

func reconcile() -> void:
    if live_serial >= 0 and not queue.has_take(live_serial):
        live_serial = -1
    if armed_serial >= 0 and not queue.has_take(armed_serial):
        armed_serial = -1
        armed_segment_id = ""
        arm_acknowledged = false
        arm_rollback.clear()
    if paused_owner >= 0 and not queue.has_take(paused_owner):
        paused_owner = -1

func transport_owner(opening: float, world: float,
        may_be_provisional: bool) -> int:
    for candidate in [paused_owner,live_serial,armed_serial]:
        var owner_serial: int = int(candidate)
        if owner_serial >= 0 and queue.has_take(owner_serial):
            return owner_serial
    if not last_take.is_empty():
        var bound_index: int = Admission.select(
            queue.online,"bound",opening,world,0.0,0.0,last_take)
        if bound_index >= 0:
            return int(queue.online[bound_index].get("take_owner",
                queue.online[bound_index]["serial"]))
    if may_be_provisional:
        # In-flight Play/Resume can leave only a prepared or armed source.
        # The oldest one is the current take, never the speculative suffix.
        for item in queue.online:
            if str(item.get("kind","source")) != "source":
                continue
            var key: String = str(item.get("take_key",""))
            if key == "prepared" or key.begins_with("armed:"):
                return int(item.get("take_owner",item["serial"]))
    return -1

func bind_segment(segment_id: String) -> bool:
    if segment_id.is_empty() or armed_serial < 0 or arm_rollback.is_empty():
        return false
    armed_segment_id = segment_id
    return true

func acknowledge_arm() -> bool:
    if armed_serial < 0 or arm_rollback.is_empty():
        return false
    arm_acknowledged = true
    return true

## The queue is the only owner of suffix retraction.  Its associated
## take identities are reconciled in this same transaction.

func observe_transport(facts: StreamGeometry, world: float, opening: float,
        graded_beat: float, key: String, phase: String,
        paused_now: bool, running_now: bool, running_reported: bool,
        expected_segment: String, allow_admission: bool,
        withdraw_future: Callable, cancel: Callable) -> void:
    if paused_now:
        if not was_paused:
            paused_owner = transport_owner(opening,world,running_reported)
        # Never withdraw the paused musical take's own unexpired source
        # strips. Its authenticated owner is protected even when the
        # future notehead has not yet crossed the right viewport edge.
        # A completely unknown owner fails closed (no suffix withdrawal);
        # only a separately identified speculative successor may retract.
        if allow_admission and armed_serial < 0 and paused_owner >= 0:
            withdraw_future.call(facts,"pause",paused_owner)
        was_paused = true
        live_serial = -1
    elif allow_admission and not running_now and phase in [
            "feedback","recovering","preview_gap","review"]:
        # Only the playback coordinator may authorize a successor.
        withdraw_future.call(facts,"changed_practice_decision")
    elif allow_admission and running_now and phase in [
            "count_in","playing","guided_wait"]:
        if key != last_take or was_paused:
            live_serial = -1
            if armed_serial >= 0:
                # An old state poll must never claim an unacknowledged
                # Play/Resume/Retry or one from another segment.
                if arm_acknowledged and not expected_segment.is_empty() and \
                        armed_segment_id == expected_segment:
                    if StreamLifecycle.activate(
                            queue.online,armed_serial,key,false,
                            int(arm_rollback.get("predecessor_owner",-1))):
                        live_serial = armed_serial
                        live_segment_id = expected_segment
                        last_take = key
                        arm_rollback.clear()
                        arm_acknowledged = false
                        armed_serial = -1
                        armed_segment_id = ""
                    else:
                        cancel.call(facts,world)
            elif key == last_take and not was_paused:
                var owned: int = Admission.select(
                    queue.online,"bound",opening,world,0.0,0.0,key)
                if owned >= 0:
                    live_serial = int(queue.online[owned].get(
                        "take_owner",queue.online[owned]["serial"]))
        was_paused = false
        paused_owner = -1
    elif not paused_now:
        live_serial = -1

## The stream ledger is also the sole owner of failed-arm compensation.
## Unexposed geometry is restored exactly, while visible strips remain
## immutable.  The view provides retained assets and schedules redraw only.

func cancel(facts: StreamGeometry, world: float, canvas: Control, restore: Callable) -> bool:
    # Only an unacknowledged reservation may be rolled back. Once published,
    # the world coordinates are immutable and its notes must exit normally.
    if arm_rollback.is_empty():
        return false
    var owner_serial: int = int(arm_rollback["owner_serial"])
    var withdrawn_suffix: Array = arm_rollback.get("withdrawn_suffix",[])
    if armed_serial != owner_serial:
        arm_rollback.clear()
        return false
    var restored: bool = false
    if bool(arm_rollback.get("newly_allocated",false)):
        queue.withdraw_take_tail(
            canvas,owner_serial,world,facts.density,
            facts.gap,facts.duration,facts.width,
            facts.playhead,"failed_command")
        restored = not queue.has_take(owner_serial)
    else:
        restored = StreamLifecycle.restore_owner(queue.online,
            owner_serial,arm_rollback["source_snapshot"])
    live_serial = int(arm_rollback["old_live_serial"])
    armed_serial = -1
    armed_segment_id = ""
    arm_acknowledged = false
    arm_rollback.clear()
    if not withdrawn_suffix.is_empty():
        restored = restore.call(facts,withdrawn_suffix,world) and restored
    canvas.queue_redraw()
    return restored

func arm(facts: StreamGeometry, generation: int, append: Callable, reserve: Callable,
        reject: Callable, cancel: Callable, empty_onset: Callable, retry_placement: bool,
        world: float, opening: float, right: float,
        header: float, planned_start_world: float = NAN,
        retrying: bool = false, empty_strip_count_in: float = 0.0,
        exact_authorized: bool = false) -> Dictionary:
    # The common future-only admission route owns a rollback snapshot until
    # the backend confirms the newly armed transport. Failure returns all
    # source/rest clip roles to their exact original state.
    if not facts.ready:
        return {}
    var old_live: int = live_serial
    var serial_before: int = generation
    var candidate_serial := -1
    # Paused musical identity is protected by the immutable queue's
    # predecessor owner, never physically restarted at its frozen origin.
    # Resume always appends a fresh backend-authorized count-in source.
    if candidate_serial < 0 and is_finite(planned_start_world):
        var checked: float = planned_start_world if exact_authorized else Admission.position(queue.online,
            facts.world,right,
            header,planned_start_world,0.0,
            facts.density,facts.gap,facts.duration)
        # An exact automatic continuation may be preflighted as an
        # announced empty-strip opening. Do not reinterpret the one fixed
        # deadline as an offscreen append after that physical proof.
        var onto_empty_strip: bool = exact_authorized and \
            empty_strip_count_in > 0.0
        if not is_finite(checked) and retry_placement:
            # A Retry is placed by Admission.retry_start (right edge at
            # once, after exposed ink, no REST_GAP/READY travel): the commit
            # accepts exactly that slot (the preflight's own rule).
            var retry_floor: float = Admission.retry_start(
                queue.online,facts.world,right,
                header,float(facts.rest_gap),
                facts.density,facts.gap,facts.duration)
            if planned_start_world >= retry_floor-.0001:
                checked = planned_start_world
        if not is_finite(checked) and empty_strip_count_in > 0.0:
            # The preflight chose the empty-strip count-in bar slot; the
            # live queue must still permit exactly that deadline.
            var earliest: float = empty_onset.call(
                queue.online,facts.world,empty_strip_count_in,
                header,maxf(1.0,facts.density),
                facts.gap,facts.duration,
                facts.width,facts.playhead)
            onto_empty_strip = is_finite(earliest) and \
                planned_start_world >= earliest-.0001
            checked = planned_start_world if onto_empty_strip else NAN
        if not is_finite(checked):
            return {}
        candidate_serial = int(append.call(
            facts,opening,checked,opening,"prepared",onto_empty_strip))
        if candidate_serial < 0:
            return {}
    elif candidate_serial < 0:
        candidate_serial = reserve.call(facts,facts.world,opening,right,header)
    if candidate_serial < 0:
        return {}
    var snapshot: Dictionary = StreamLifecycle.snapshot_owner(
        queue.online,candidate_serial)
    if snapshot.is_empty():
        reject.call(facts,candidate_serial,serial_before,old_live,{})
        return {}
    # Every unacknowledged control has a unique owner-scoped identity.
    if not StreamLifecycle.activate(
            queue.online,candidate_serial,"armed:%d" % candidate_serial,true):
        reject.call(facts,candidate_serial,serial_before,old_live,snapshot)
        return {}
    armed_serial = candidate_serial
    armed_segment_id = ""
    arm_acknowledged = false
    arm_rollback = {
        "owner_serial":candidate_serial,"source_snapshot":snapshot,
        "newly_allocated":candidate_serial > serial_before,
        "predecessor_owner":paused_owner if was_paused else -1,
        "old_live_serial":old_live}
    for item in queue.online:
        if int(item.get("serial",-1)) == candidate_serial:
            return {"start_world":float(item["world_origin"])+opening,
                "opening":opening}
    cancel.call(facts,facts.world)
    return {}

## Exact-deadline recovery preparation and commit live on the same
## immutable stream ledger as Play/Resume/Retry, with no second FIFO.

func live_owner() -> int:
    return live_serial

func restore_live(owner: int) -> void:
    live_serial = owner

func release_live() -> void:
    live_serial = -1

func admitted(owner: int) -> void:
    live_serial = owner

func remember_withdrawn_suffix(previous: Array) -> void:
    arm_rollback["withdrawn_suffix"] = previous

func has_armed_reservation() -> bool:
    return armed_serial >= 0 and arm_acknowledged

func bound_segment() -> String:
    return live_segment_id

func owns_authorized_segment(segment_id: String) -> bool:
    # The physical source may be ACKed but not yet promoted by the next
    # state-poll observation. Both states must prove ownership of an
    # existing queue take, not merely preserve a matching string.
    if segment_id.is_empty():
        return false
    if (live_segment_id == segment_id and live_serial >= 0
            and queue.has_take(live_serial)):
        return true
    return (armed_segment_id == segment_id and arm_acknowledged
        and armed_serial >= 0 and not arm_rollback.is_empty()
        and queue.has_take(armed_serial))

func status(generation: int) -> Dictionary:
    return {"generation":generation,"live_serial":live_serial,
        "armed_serial":armed_serial,"last_take":last_take,
        "bound_segment_id":live_segment_id}

func preflight() -> Dictionary:
    return {"was_paused":was_paused,
        "paused_owner":paused_owner,"last_take":last_take}

func observe_state(facts: StreamGeometry, state: Dictionary, graded_beat: float,
        allow_admission: bool, withdraw_future: Callable, cancel: Callable) -> void:
    var phase: String = str(state.get("phase",""))
    var mode: String = str(state.get("mode","practice"))
    var opening: float = maxf(0.0,float(state.get("play_from_beat",0.0)))
    var published_timeline: Variant = state.get("playback_timeline")
    var expected_segment: String = (
        str(published_timeline.get("segment_id",""))
        if published_timeline is Dictionary else "")
    var key: String = "%s|%d|%d|%s" % [
        str(state.get("piece_fingerprint","")),
        int(state.get("revision",-1)),
        int(state.get("transport_id",-1)),mode]
    var paused_now: bool = bool(state.get("paused",false))
    var running_now: bool = bool(state.get("running",false)) and not paused_now
    observe_transport(
        facts,facts.world,opening,graded_beat,key,phase,
        paused_now,running_now,bool(state.get("running",false)),
        expected_segment,allow_admission,withdraw_future,cancel)
    # Invariant: a graded or audible take that is playing has its own source
    # bound on the staff. A take without one is a defect, never a state to
    # show silently as an empty staff (practice flow, 2026-11-18).
    if running_now and phase == "playing" and mode in ["practice","perform","listen"] \
            and (expected_segment.is_empty() or \
                 bound_segment() != expected_segment):
        if unscored_take != key:
            unscored_take = key
            push_error("TAKE_WITHOUT_SCORE: %s expected_segment=%s bound_segment=%s" % [
                key, expected_segment, bound_segment()])
