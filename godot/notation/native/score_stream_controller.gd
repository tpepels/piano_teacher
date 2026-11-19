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

func owner_status() -> Dictionary:
    return {"generation":serial,"live_serial":live_serial,
        "armed_serial":armed_serial,"last_take":last_take,
        "bound_segment_id":live_segment_id}


func has_take(owner_serial: int) -> bool:
    return queue.has_take(owner_serial)


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



## Append a complete source/rest take into the one immutable stream FIFO.
## The renderer provides authenticated source windows and measured glyph
## context. Nothing else can allocate source serials or publish a partial
## admitted owner.
func append_take(view, windows: Array[Vector2], source_beat: float,
        start_world: float, take_key: String, empty_strip: bool,
        first_header_spaces: float, rest_gap: float) -> void:
    last_admitted = -1
    var first_serial: int = serial+1
    var original_origin: float = start_world-source_beat
    var hidden: bool = take_key == "prepared"
    if windows.is_empty():
        return
    var density: float = maxf(1.0,view.timeline.pixels_per_beat)
    var gap_pixels: float = view.staff_gap()
    var duration: float = view.timeline.duration_beats
    var width: float = view.size.x
    var added := 0
    for index in range(windows.size()):
        var bounds: Vector2 = windows[index]
        var is_first: bool = index == 0
        var is_last: bool = index == windows.size()-1
        var strip_serial: int = first_serial+index
        # Source cuts are authenticated musical beats, with only visual
        # contextual margins computed by the source-geometry owner.
        var leading_spaces: float = (
            first_header_spaces if bounds.x <= .0001 else 1.6
            ) if is_first else 0.0
        var specs: Array = [{
            "kind":"source","owner_serial":strip_serial,
            "take_owner":first_serial,
            "world_origin":original_origin,
            "source_floor":bounds.x,"source_ceiling":bounds.y,
            "clip_floor":bounds.x,"clip_ceiling":bounds.y,
            "clip_leading_spaces":leading_spaces,
            "clip_trailing_spaces":2.2 if is_last else 0.0,
            "piece_duration":duration,"take_key":take_key,
            "pending":take_key in ["prepared","autopending"],
            "hidden_until_armed":hidden}]
        if is_last and rest_gap > .0001:
            specs.append({
                "kind":"rest","owner_serial":strip_serial,
                "take_owner":first_serial,
                "world_origin":original_origin+duration,
                "source_floor":0.0,"source_ceiling":rest_gap,
                "take_key":"rest","pending":false,
                "hidden_until_armed":hidden})
        if not queue.enqueue(view,specs,
                view.retained_repeat_segments,view.retained_rest_segments,
                view.retained_first_once,view.stream_world_beat,width,
                width*view.PLAYHEAD_FRACTION,density,gap_pixels,
                duration,empty_strip):
            # Do not leave a partial, ungraded take after a failed append.
            if added > 0:
                queue.withdraw_take_tail(view,first_serial,
                    view.stream_world_beat,density,gap_pixels,duration,width,
                    width*view.PLAYHEAD_FRACTION,"failed_take_batch")
                if queue.has_take(first_serial):
                    push_error("Cannot safely roll back incomplete streamed take")
            push_error("Refused immutable score strip admission %d" % strip_serial)
            return
        added += 1
    serial = first_serial+windows.size()-1
    live_serial = first_serial
    last_admitted = first_serial


## Single transport reservation authority for Play, Resume, Retry, and
## pre-ACK paused source reuse. A view exposes only source geometry.
func reserve_ready(view, world: float, opening: float,
        right: float, header: float) -> int:
    if not view.native_ready or not view.retained_ready() or \
            opening >= view.timeline.duration_beats:
        return -1
    var index: int = Admission.select(
        queue.online,"ready",opening,world,right,header)
    if index >= 0:
        return int(queue.online[index]["serial"])
    # READY never edits an existing placement. If its hidden source has
    # approached the display, withdraw the still-unexposed tail into the
    # offline queue, then append a fresh immutable future reservation.
    var stale: int = Admission.select(
        queue.online,"idle",opening,world)
    if stale >= 0:
        var stale_serial: int = int(queue.online[stale]["serial"])
        var removed: Array[int] = queue.withdraw_tail(
            view,world,view.timeline.pixels_per_beat,view.staff_gap(),
            view.timeline.duration_beats,view.size.x,view.size.x*view.PLAYHEAD_FRACTION,
            "idle_expired")
        if not removed.has(stale_serial):
            # The old reservation has crossed its immutable exposure
            # boundary. Retain it and append beyond its printed end.
            # Returning -1 here strands Pause -> Resume at low BPM.
            pass
    var onset: float = Admission.position(queue.online,world,right,
        header,NAN,Admission.READY_TRAVEL_BEATS,
        view.timeline.pixels_per_beat,view.staff_gap(),view.timeline.duration_beats)
    # A new stage may be ready while prior lesson ink is still moving.
    # Choose a later offscreen origin instead of repeatedly rejecting Play.
    var peer_floor: float = queue.minimum_peer_opening(
        view.timeline.pixels_per_beat,view.size.x,view.size.x*view.PLAYHEAD_FRACTION)
    if is_finite(peer_floor):
        onset = maxf(onset,peer_floor+header+
            Admission.REST_GAP_BEATS)
    if not is_finite(onset):
        return -1
    var old_serial := serial
    view.append_source_take(opening,onset,opening,"prepared")
    if serial == old_serial:
        return -1
    live_serial = -1
    return last_admitted


func claim_pending_auto(world: float, opening: float,
        right: float, header: float) -> int:
    var index: int = Admission.select(queue.online,"automatic",
        opening,world,right,header)
    return int(queue.online[index].get("take_owner",
        queue.online[index]["serial"])) if index >= 0 else -1


func reject_candidate(view, owner_serial: int, before_serial: int,
        old_live_serial: int, snapshot: Dictionary) -> void:
    # A failed pre-commit reservation must not leave a speculative future
    # source/rest pair occupying the musical axis.
    if owner_serial > before_serial:
        queue.withdraw_take_tail(view,owner_serial,view.stream_world_beat,
            view.timeline.pixels_per_beat,view.staff_gap(),view.timeline.duration_beats,
            view.size.x,view.size.x*view.PLAYHEAD_FRACTION,"rejected_admission")
    elif not snapshot.is_empty():
        StreamLifecycle.restore_owner(queue.online,owner_serial,snapshot)
    live_serial = old_live_serial



func arm_take(view, world: float, opening: float, right: float,
        header: float, planned_start_world: float = NAN,
        resuming_paused: bool = false, retrying: bool = false,
        empty_strip_count_in: float = 0.0) -> Dictionary:
    # The common future-only admission route owns a rollback snapshot until
    # the backend confirms the newly armed transport. Failure returns all
    # source/rest clip roles to their exact original state.
    if not view.native_ready or not view.retained_ready():
        return {}
    view.stream_world_beat = maxf(view.stream_world_beat,world)
    var old_live: int = live_serial
    var serial_before: int = self.serial
    var candidate_serial := -1
    var reused := false
    var reused_auto := false
    var reused_unplayed := false
    if resuming_paused and was_paused and \
            absf(opening-paused_source) < .0001:
        var paused_index: int = Admission.select(queue.online,"paused",
            opening,view.stream_world_beat,0.0,0.0,last_take)
        if paused_index < 0 and paused_owner >= 0:
            # Pause can precede the preceding Play's transport ACK. In that
            # race the armed owner's key is provisional, but its immutable
            # source and future location are already authoritative.
            for index in range(queue.online.size()):
                var candidate: Dictionary = queue.online[index]
                if str(candidate.get("kind","")) != "source" or \
                        int(candidate.get("take_owner",-1)) != paused_owner:
                    continue
                if str(candidate.get("take_key","")).begins_with("armed:") and \
                        absf(float(candidate.get("source_floor",-1))-opening) < .00001 and \
                        float(candidate["world_origin"])+opening >= \
                            view.stream_world_beat+Admission.PAUSED_REUSE_EPSILON_BEATS:
                    paused_index = index
                    break
        if paused_index >= 0:
            candidate_serial = int(queue.online[paused_index].get("take_owner",
                queue.online[paused_index]["serial"]))
            reused = true
            reused_unplayed = true
    if candidate_serial < 0 and (resuming_paused or retrying):
        candidate_serial = claim_pending_auto(view.stream_world_beat,opening,right,header)
        reused_auto = candidate_serial >= 0
        reused = reused_auto
    if candidate_serial < 0 and is_finite(planned_start_world):
        var checked: float = Admission.position(queue.online,
            view.stream_world_beat,right,
            header,planned_start_world,0.0,
            view.timeline.pixels_per_beat,view.staff_gap(),view.timeline.duration_beats)
        var onto_empty_strip := false
        if not is_finite(checked) and retry_placement:
            # A Retry is placed by Admission.retry_start (right edge at
            # once, after exposed ink, no REST_GAP/READY travel): the commit
            # accepts exactly that slot (the preflight's own rule).
            var retry_floor: float = Admission.retry_start(
                queue.online,view.stream_world_beat,right,
                header,float(view.practice_timeline.get(
                    "gap",{}).get("duration_beats",0.0)),
                view.timeline.pixels_per_beat,view.staff_gap(),view.timeline.duration_beats)
            if planned_start_world >= retry_floor-.0001:
                checked = planned_start_world
        if not is_finite(checked) and empty_strip_count_in > 0.0:
            # The preflight chose the empty-strip count-in bar slot; the
            # live queue must still permit exactly that deadline.
            var earliest: float = view.empty_strip_onset(
                queue.online,view.stream_world_beat,empty_strip_count_in,
                header)
            onto_empty_strip = is_finite(earliest) and \
                planned_start_world >= earliest-.0001
            checked = planned_start_world if onto_empty_strip else NAN
        if not is_finite(checked):
            return {}
        var previous_serial := self.serial
        view.append_source_take(opening,checked,opening,"prepared",onto_empty_strip)
        if self.serial == previous_serial:
            return {}
        candidate_serial = last_admitted
    elif candidate_serial < 0:
        candidate_serial = reserve_ready(view,view.stream_world_beat,opening,right,header)
    if candidate_serial < 0:
        return {}
    var snapshot: Dictionary = StreamLifecycle.snapshot_owner(
        queue.online,candidate_serial)
    if snapshot.is_empty():
        reject_candidate(view,candidate_serial,serial_before,old_live,{})
        return {}
    # Every unacknowledged control has a unique owner-scoped identity.
    if not StreamLifecycle.activate(
            queue.online,candidate_serial,"armed:%d" % candidate_serial,true):
        reject_candidate(view,candidate_serial,serial_before,old_live,snapshot)
        return {}
    armed_serial = candidate_serial
    armed_segment_id = ""
    arm_acknowledged = false
    arm_rollback = {
        "owner_serial":candidate_serial,"source_snapshot":snapshot,
        "newly_allocated":self.serial > serial_before,
        "old_live_serial":old_live}
    for item in queue.online:
        if int(item.get("serial",-1)) == candidate_serial:
            return {"start_world":float(item["world_origin"])+opening,
                "opening":opening,"reused":reused,
                "reused_unplayed_count_in":reused_unplayed}
    cancel_arm(view,view.stream_world_beat)
    return {}



## Exact-deadline recovery preparation and commit live on the same
## immutable stream ledger as Play/Resume/Retry, with no second FIFO.
func schedule_recovery(view, world: float, source_opening: float,
        graded_deadline_world: float, right: float, header: float,
        plan_id: String = "",
        allow_count_in: bool = false, count_in_beats: float = 0.0,
        deadline_at_or_after: bool = false, untimed: bool = false) -> bool:
    # Recovery decisions arrive from the engine with an absolute graded
    # deadline. Reuse a compatible offline-planned future if possible;
    # otherwise withdraw the maximal safe suffix, then APPEND new source
    # notation at that exact deadline. A late deadline must never cause
    # an onscreen pop or independent renderer camera adjustment.
    if not view.native_ready or not view.retained_ready() or \
            not is_finite(graded_deadline_world) or \
            source_opening < 0.0 or source_opening >= view.timeline.duration_beats:
        return false
    view.stream_world_beat = maxf(view.stream_world_beat,world)
    var identity: String = plan_id if not plan_id.is_empty() else \
        "%.6f:%.6f" % [source_opening,graded_deadline_world]
    if planned_ids.has(identity):
        # The plan identity names its source opening, graded take and exact
        # backend deadline: the owner admitted for it IS that take's ink.
        # A tail withdrawal can invalidate it; then admit it again.
        if queue.has_take(int(planned_ids[identity])):
            return true
        planned_ids.erase(identity)
    # An already elapsed plan may no longer be reinserted: it would
    # introduce notes behind the real playhead.
    if graded_deadline_world <= view.stream_world_beat:
        diagnose_plan(identity,"elapsed",graded_deadline_world,view.stream_world_beat)
        return false
    # PREPARE: check the actual exact deadline against the queue AFTER
    # maximal safe tail withdrawal, without mutating the live queue.
    # Previously this check ran AFTER view.trim_future_queue(), so a late or
    # impossible engine deadline deleted valid pending music first.
    var preview: Dictionary = queue.preview_tail_withdrawal(
        view.stream_world_beat,view.timeline.pixels_per_beat,view.staff_gap(),
        view.timeline.duration_beats,view.size.x,view.size.x*view.PLAYHEAD_FRACTION)
    var remaining: Array = preview["remaining"]
    var checked: float = Admission.position(remaining,
        view.stream_world_beat,right,
        header,
        graded_deadline_world,0.0,view.timeline.pixels_per_beat,
        view.staff_gap(),view.timeline.duration_beats)
    var on_empty := false
    if untimed:
        # Untimed guided Learn grades no deadline: the learner plays each
        # note when ready. Open the passage at the first append-only slot
        # that starts offscreen, never before the engine's announcement.
        var earliest: float = Admission.position(remaining,
            view.stream_world_beat,right,
            header,NAN,0.0,
            view.timeline.pixels_per_beat,view.staff_gap(),view.timeline.duration_beats)
        checked = maxf(graded_deadline_world,earliest) if is_finite(earliest) else NAN
    elif not is_finite(checked) and allow_count_in:
        # The initial command or an already announced backend continuation
        # may use the empty-staff slot; source/rest/peer physical clearance
        # remains mandatory. Practice plans have been announced BEFORE this
        # snapshot, so a partial count-in has already elapsed. The first
        # note still has a guaranteed future reading lead and retains its
        # exact original grading deadline.
        if deadline_at_or_after:
            var density: float = maxf(1.0,view.timeline.pixels_per_beat)
            var playhead: float = view.size.x*view.PLAYHEAD_FRACTION
            checked = Admission.announced_empty_strip_start(
                remaining,view.stream_world_beat,count_in_beats,
                header,graded_deadline_world,
                queue.minimum_peer_opening(
                    density,view.size.x,playhead,true,"source"),
                density,view.staff_gap(),view.timeline.duration_beats,
                queue.minimum_peer_opening(
                    density,view.size.x,playhead,true,"rest"))
            on_empty = is_finite(checked)
        else:
            # Listen/Perform/Learn use one initial full count-in slot, with
            # the original tight timestamp-to-slot equality requirement.
            var onset: float = view.empty_strip_onset(
                remaining,view.stream_world_beat,count_in_beats,
                header)
            if is_finite(onset) and absf(onset-graded_deadline_world) <= \
                    Admission.EMPTY_STRIP_DEADLINE_EPSILON_BEATS:
                checked = graded_deadline_world
                on_empty = true
    if not is_finite(checked):
        var blocking: Array = []
        for item in remaining:
            var bounds: Vector2 = Admission.clip_bounds(item,
                view.timeline.pixels_per_beat,view.staff_gap(),view.timeline.duration_beats)
            var finish: float = float(item["world_origin"])+bounds.y/ \
                maxf(1.0,view.timeline.pixels_per_beat)
            if finish > view.stream_world_beat-1.0:
                blocking.append([str(item.get("kind","source")),
                    snappedf(finish,.001)])
        var detail: Dictionary = {"count_in":count_in_beats,
            "header":header,
            "deadline_lead":graded_deadline_world-view.stream_world_beat,
            "ink_ends":blocking}
        var diagnostic_density: float = maxf(1.0,view.timeline.pixels_per_beat)
        var diagnostic_playhead: float = view.size.x*view.PLAYHEAD_FRACTION
        var peer_source: float = queue.minimum_peer_opening(
            diagnostic_density,view.size.x,diagnostic_playhead,true,"source")
        var peer_rest: float = queue.minimum_peer_opening(
            diagnostic_density,view.size.x,diagnostic_playhead,true,"rest")
        if is_finite(peer_source):
            detail["peer_source_floor"] = peer_source
        if is_finite(peer_rest):
            detail["peer_rest_floor"] = peer_rest
        diagnose_plan(identity,"refused_inside_or_overlap",
            graded_deadline_world,view.stream_world_beat,detail)
        return false
    var incoming_left: float = checked - header
    if not queue.clears_prior_layers(incoming_left,
            view.timeline.pixels_per_beat,view.size.x,view.size.x*view.PLAYHEAD_FRACTION,on_empty):
        diagnose_plan(identity,"refused_prior_layer",graded_deadline_world,view.stream_world_beat)
        return false
    # COMMIT: the exact same exposure snapshot and world coordinate must
    # still hold. No yield/poll/other input runs between preview and commit.
    var saved_suffix: Array = []
    for index in range(remaining.size(),queue.online.size()):
        saved_suffix.append(queue.online[index].duplicate())
    var prior_live: int = live_serial
    view.trim_future_queue("recovery_replan")
    if queue.online.size() != remaining.size():
        # The archive may refuse one of several suffix withdrawals after
        # earlier owners were already removed. Restore ONLY the missing
        # original tail; re-enqueueing the still-online survivors would
        # duplicate their immutable notes and fail recovery altogether.
        var still_present: int = maxi(0,
            queue.online.size()-remaining.size())
        push_error("RECOVERY_TRANSACTION: tail withdrawal incomplete")
        restore_future_suffix(view,saved_suffix.slice(still_present),
            view.stream_world_beat)
        live_serial = prior_live
        return false
    var before: int = self.serial
    view.append_source_take(source_opening,checked,source_opening,
        "autopending",on_empty)
    live_serial = prior_live
    if self.serial > before:
        planned_ids[identity] = last_admitted
        planned_openings[identity] = checked
        diagnose_plan(identity,"admitted",checked,
            view.stream_world_beat,{"owner":last_admitted,"on_empty_strip":on_empty})
        return true
    # If a retained segment/asset failed halfway through its measure batch,
    # eliminate that exact unexposed newly allocated owner first. Its serial
    # was not committed by _stream_add_take; the pre-existing suffix retains
    # the only authoritatively valid music at its original world positions.
    var partial_owner: int = before+1
    if queue.has_take(partial_owner):
        queue.withdraw_take_tail(view,partial_owner,
            view.stream_world_beat,view.timeline.pixels_per_beat,view.staff_gap(),
            view.timeline.duration_beats,view.size.x,view.size.x*view.PLAYHEAD_FRACTION,
            "recovery_incomplete_append")
    if queue.has_take(partial_owner):
        push_error("RECOVERY_TRANSACTION: incomplete take cannot be rolled back")
        return false
    restore_future_suffix(view,saved_suffix,view.stream_world_beat)
    live_serial = prior_live
    return false


