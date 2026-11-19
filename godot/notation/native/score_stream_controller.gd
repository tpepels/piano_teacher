extends RefCounted
## Sole mutable ledger of this renderer revision's note/rest streams.
## The retained queue enforces immutable on-screen geometry and safe
## append/withdraw. View performs drawing and passes geometry capabilities.
## Physical admission operates on this ledger; a repaint never resets it.
const StreamQueue := preload("res://score_stream_queue.gd")
const Admission := preload("res://score_stream_admission.gd")
const StreamLifecycle := preload("res://notation/native/stream_lifecycle.gd")

var queue = StreamQueue.new()
var last_take := ""
var was_paused := false
var paused_source := 0.0
var paused_owner := -1
var live_serial := -1
var armed_serial := -1
var armed_segment_id := ""
var live_segment_id := ""
var arm_rollback: Dictionary = {}
var arm_acknowledged := false
var serial := 0
var last_admitted := -1
var planned_ids: Dictionary = {}
var planned_openings: Dictionary = {}
var retry_placement := false

func reset(view) -> void:
    # No direct queue array replacement: the queue first releases its own
    # previously visible/archived retained source strips and peer references.
    queue.reset(view)
    planned_ids.clear()
    planned_openings.clear()
    last_take = ""
    was_paused = false
    paused_source = 0.0
    paused_owner = -1
    live_serial = -1
    armed_serial = -1
    armed_segment_id = ""
    live_segment_id = ""
    arm_rollback.clear()
    arm_acknowledged = false
    last_admitted = -1
    retry_placement = false

func register_predecessor(previous) -> void:
    queue.register_peer(previous)

func online_snapshot() -> Array:
    # Admission PREPARE reads a frozen copy, never the live FIFO array.
    return queue.online.duplicate(true)

func online_size() -> int:
    return queue.online.size()

func remember_withdrawn_suffix(previous: Array) -> void:
    # Rollback is owned by the stream ledger. The native executor may
    # attach only the exact suffix removed by its immediately preceding
    # successful preflight.
    arm_rollback["withdrawn_suffix"] = previous

func retry_placement_enabled(enabled: bool) -> void:
    retry_placement = enabled

func queue_generation() -> int:
    return serial

func bound_segment() -> String:
    return live_segment_id

func has_armed_reservation() -> bool:
    return armed_serial >= 0 and arm_acknowledged

## A peer can inspect immutable physical clearance facts, not this queue's
## live nodes, serials or rollback state.  This value is recomputed at
## preflight rather than retained across engraving/density changes.
func peer_clearance_facts(density: float, gap: float,
        duration: float, playhead_x: float) -> Dictionary:
    var ends: Array[Dictionary] = []
    for item in queue.online:
        var bounds: Vector2 = Admission.clip_bounds(
            item,density,gap,duration)
        ends.append({
            "rest":str(item.get("kind","source")) == "rest",
            "end_world":float(item["world_origin"])+bounds.y/density
        })
    return {"queue_id":queue.get_instance_id(),"density":density,
        "playhead_x":playhead_x,"ends":ends}

## The queue retires the earliest expired source/rest strips.  The same
## ledger owns the resulting live and armed take identities; the drawing
## view must not repair those identities from retired serials.
func prune_expired(owner: Control, world: float, density: float,
        gap: float, duration: float, playhead_x: float) -> void:
    var retired: Array[int] = queue.expire_front(
        owner,world,density,gap,duration,playhead_x)
    if retired.has(live_serial) and not queue.has_take(live_serial):
        live_serial = -1
    if retired.has(armed_serial) and not queue.has_take(armed_serial):
        armed_serial = -1
        arm_acknowledged = false
        arm_rollback.clear()

var _diagnosed_plans: Dictionary = {}

## Diagnostic deduplication belongs to the same plan ledger that records
## admissions, not to NativeScoreView's paint/repaint lifecycle.
func diagnose_plan(identity: String, outcome: String, deadline_world: float,
        world: float, extra: Dictionary = {}) -> void:
    if OS.get_environment("PIANO_TEACHER_TIMING_DIAGNOSTICS") != "1":
        return
    var seen: String = identity+"|"+outcome
    if _diagnosed_plans.has(seen):
        return
    _diagnosed_plans[seen] = true
    var row: Dictionary = {"plan_id":identity,"outcome":outcome,
        "deadline_world":deadline_world,"world":world}
    row.merge(extra,true)
    print("SCORE_PLAN_QUEUE:",JSON.stringify(row))

## The admission ledger resolves the active musical owner from public take
## identities and existing stream strips.  The view must not interpret this
## ordering independently when Pause arrives ahead of a Play ACK.
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
func trim_future(owner: Control, reason: String, world: float,
        density: float, gap: float, duration: float, width: float,
        playhead_x: float, protected_take: int = -1) -> Array[int]:
    var removed: Array[int] = queue.withdraw_tail(
        owner,world,density,gap,duration,width,playhead_x,
        reason,false,protected_take)
    if not removed.is_empty():
        if live_serial >= 0 and not queue.has_take(live_serial):
            live_serial = -1
        if armed_serial >= 0 and not queue.has_take(armed_serial):
            armed_serial = -1
            armed_segment_id = ""
            arm_acknowledged = false
            arm_rollback.clear()
        if paused_owner >= 0 and not queue.has_take(paused_owner):
            paused_owner = -1
    return removed

## One lifecycle reducer for Pause, immutable backend-ACK binding, recovery
## cancellation and normal playing/feedback snapshots. NativeScoreView only
## samples the snapshot and paints the result.
func observe_transport(owner: Control, world: float, opening: float,
        graded_beat: float, key: String, phase: String,
        paused_now: bool, running_now: bool, running_reported: bool,
        expected_segment: String, allow_admission: bool) -> void:
    if paused_now:
        if not was_paused:
            paused_source = maxf(opening,opening+graded_beat)
            paused_owner = transport_owner(opening,world,running_reported)
        if allow_admission and armed_serial < 0:
            # A provisional owner must survive until its Play ACK.
            owner.trim_future_queue("pause")
        was_paused = true
        live_serial = -1
    elif allow_admission and not running_now and phase in [
            "feedback","recovering","preview_gap","review"]:
        # Only the playback coordinator may authorize a successor.
        owner.trim_future_queue("changed_practice_decision")
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
                            queue.online,armed_serial,key,false):
                        live_serial = armed_serial
                        live_segment_id = expected_segment
                        last_take = key
                        arm_rollback.clear()
                        arm_acknowledged = false
                        armed_serial = -1
                        armed_segment_id = ""
                    else:
                        owner.cancel_stream_arm()
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
func cancel_arm(view, world: float) -> bool:
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
            view,owner_serial,world,view.timeline.pixels_per_beat,
            view.staff_gap(),view.timeline.duration_beats,view.size.x,
            view.size.x*view.PLAYHEAD_FRACTION,"failed_command")
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
        restored = restore_future_suffix(view,withdrawn_suffix,world) and restored
    view.queue_redraw()
    return restored



func restore_future_suffix(view, saved: Array, world: float) -> bool:
    # Compensation for a failed append after a validated preflight.
    # Re-enqueue the exact previously withdrawn source/rest batches in
    # chronological order; do not create any new world time or note content.
    var cursor := 0
    var restored := true
    while cursor < saved.size():
        var old: Dictionary = saved[cursor]
        var serial: int = int(old.get("owner_serial",-1))
        var batch: Array = []
        while cursor < saved.size() and \
                int(saved[cursor].get("owner_serial",-1)) == serial:
            var item: Dictionary = saved[cursor]
            var spec: Dictionary = queue._record(item)
            spec["pending"] = bool(item.get("pending",false))
            spec["hidden_until_armed"] = bool(item.get("hidden_until_armed",false))
            batch.append(spec)
            cursor += 1
        if not queue.enqueue(view,batch,
                view.retained_repeat_segments,view.retained_rest_segments,
                view.retained_first_once,world,view.size.x,view.size.x*view.PLAYHEAD_FRACTION,
                view.timeline.pixels_per_beat,view.staff_gap(),view.timeline.duration_beats):
            push_error("RECOVERY_TRANSACTION: rollback admission failed for "+str(serial))
            restored = false
            break
        for item in queue.online:
            if int(item.get("owner_serial",-1)) == serial:
                for original in saved:
                    if int(original.get("serial",0)) == int(item.get("serial",0)):
                        item["armed"] = bool(original.get("armed",false))
                        item["ever_visible"] = bool(original.get("ever_visible",false))
                        break
    return restored


