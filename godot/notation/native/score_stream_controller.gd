extends RefCounted
const StreamGeometry := preload("res://notation/native/stream_geometry.gd")
## Sole mutable ledger of this renderer revision's note/rest streams.
## The retained queue enforces immutable on-screen geometry and safe
## append/withdraw. View performs drawing and passes geometry capabilities.
## Physical admission operates on this ledger; a repaint never resets it.
const StreamQueue := preload("res://score_stream_queue.gd")
const Admission := preload("res://score_stream_admission.gd")
const StreamLifecycle := preload("res://notation/native/stream_lifecycle.gd")

var queue = StreamQueue.new()
const TakeBinding := preload("res://notation/native/stream_take_binding.gd")
var _binding = TakeBinding.new(queue)
var _canvas_ref: WeakRef
var _pool
var _source_windows: Callable

func bind_surface(canvas: Control, pool, source_windows: Callable) -> void:
    _canvas_ref = weakref(canvas)
    _pool = pool
    _source_windows = source_windows

func canvas() -> Control:
    return _canvas_ref.get_ref() if _canvas_ref != null else null

func append_source(facts: StreamGeometry, source_beat: float, start_world: float,
        from_beat: float, take_key: String, empty_strip: bool = false,
        guided: bool = false, display_context: bool = false,
        leading_rest_beats: float = 0.0) -> void:
    var windows: Array[Vector2] = _source_windows.call(maxf(0.0,from_beat))
    append_take(facts,windows,source_beat,start_world,take_key,empty_strip,
        facts.first_header_spaces,facts.rest_gap,guided,display_context,leading_rest_beats)

func trim(facts: StreamGeometry, reason: String, protected_take: int = -1,
        protected_strip: int = -1) -> Array[int]:
    return trim_future(canvas(),reason,facts.world,facts.density,facts.gap,
        facts.duration,facts.width,facts.playhead,protected_take,protected_strip)

var serial := 0
var last_admitted := -1
# True while a take the musical timeline placed is appended.
var timeline_placement := false
const RecoveryPlanner := preload("res://notation/native/stream_recovery_planner.gd")
var _recovery = RecoveryPlanner.new()

func reset() -> bool:
    # No direct queue array replacement: the queue first releases its own
    # previously visible/archived retained source strips and peer references.
    if not queue.reset(canvas()):
        return false
    _recovery.reset()
    _binding.reset()
    last_admitted = -1
    return true

func register_predecessor(previous) -> void:
    queue.register_peer(previous)

func online_snapshot() -> Array:
    # Admission PREPARE reads a frozen copy, never the live FIFO array.
    return queue.online.duplicate(true)

func bind_source(candidate: Dictionary, prepared_key: String = "") -> bool:
    # Production jobs hash the validated immutable score before installation.
    # Geometry-only test fixtures can still compute the key here.
    var key: String = prepared_key if not prepared_key.is_empty() else StreamQueue.source_identity(candidate)
    return queue.bind_score(key)

func source_identity_error() -> String:
    return queue.last_error

func online_size() -> int:
    return queue.online.size()

## The renderer owns header and source glyph measurement; only this
## stream ledger may snapshot an immutable physical withdrawal preview.
## No cross-component caller reads the private live queue or peer registry.
func preflight_facts(world: float, opening: float, source_exists: bool,
        right: float, header: float, density: float, gap: float,
        duration: float, width: float, playhead: float) -> Dictionary:
    var preview: Dictionary = queue.preview_tail_withdrawal(
        world,density,gap,duration,width,playhead)
    var facts: Dictionary = {
        "source_exists":source_exists,
        "online":online_snapshot(),
        "withdrawn":preview.duplicate(true),
        "peer_floor":queue.minimum_peer_opening(density,width,playhead),
        "peer_source_floor":queue.minimum_peer_opening(density,width,playhead,true,"source"),
        "peer_rest_floor":queue.minimum_peer_opening(density,width,playhead,true,"rest"),
        "right":right,
        "header":header,
        "preview_world":world,
    }
    var binding: Dictionary = _binding.preflight()
    facts.merge(binding)
    if bool(binding["was_paused"]) and int(binding["paused_owner"]) >= 0:
        # A fresh Resume count-in may need a new copy, but the paused
        # source's unexpired head remains immutable even while offscreen.
        # Protect only its first retained measure; later unseen measures
        # can still withdraw rather than making a whole-piece Resume wait
        # through the abandoned remainder.
        for item in queue.online:
            if str(item.get("kind","")) == "source" and \
                    int(item.get("take_owner",-1)) == int(binding["paused_owner"]):
                var protected_strip: int = queue.owner_id(item)
                facts["resume_protected_strip"] = protected_strip
                facts["resume_withdrawn"] = queue.preview_tail_withdrawal(
                    world,density,gap,duration,width,playhead,-1,false,
                    protected_strip).duplicate(true)
                break
    return facts

func queue_generation() -> int:
    return serial

func owner_status() -> Dictionary:
    return _binding.status(serial)

func has_take(owner_serial: int) -> bool:
    return queue.has_take(owner_serial)

func bound_segment() -> String:
    return _binding.bound_segment()

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

func prune_expired(owner: Control, world: float, density: float,
        gap: float, duration: float, playhead_x: float) -> void:
    queue.expire_front(
        owner,world,density,gap,duration,playhead_x)
    _binding.reconcile()

func trim_future(owner: Control, reason: String, world: float,
        density: float, gap: float, duration: float, width: float,
        playhead_x: float, protected_take: int = -1,
        protected_strip: int = -1) -> Array[int]:
    var removed: Array[int] = queue.withdraw_tail(
        owner,world,density,gap,duration,width,playhead_x,
        reason,false,protected_take,protected_strip)
    if not removed.is_empty():
        _binding.reconcile()
    return removed

## One lifecycle reducer for Pause, immutable backend-ACK binding, recovery
## cancellation and normal playing/feedback snapshots. NativeScoreView only
## samples the snapshot and paints the result.
func observe_transport(facts: StreamGeometry, world: float, opening: float,
        graded_beat: float, key: String, phase: String,
        paused_now: bool, running_now: bool, running_reported: bool,
        expected_segment: String, allow_admission: bool) -> void:
    _binding.observe_transport(facts,world,opening,graded_beat,key,phase,
        paused_now,running_now,running_reported,expected_segment,allow_admission,
        trim,cancel_arm)

func cancel_arm(facts: StreamGeometry, world: float) -> bool:
    return _binding.cancel(facts,world,canvas(),restore_future_suffix)

func restore_future_suffix(facts: StreamGeometry, saved: Array, world: float) -> bool:
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
            var spec: Dictionary = queue.source_record(item)
            spec["pending"] = bool(item.get("pending",false))
            spec["hidden_until_armed"] = bool(item.get("hidden_until_armed",false))
            batch.append(spec)
            cursor += 1
        if not queue.enqueue(canvas(),batch,
                _pool.repeat_segments,_pool.rest_segments,
                _pool.first_once,world,facts.width,facts.playhead,
                facts.density,facts.gap,facts.duration,false,_pool.allocate):
            push_error("RECOVERY_TRANSACTION: rollback admission failed for "+str(serial))
            restored = false
            break
        for item in queue.online:
            if int(item.get("owner_serial",-1)) == serial:
                for original in saved:
                    if str(original.get("slot_id","")) == str(item.get("slot_id","")):
                        item["armed"] = bool(original.get("armed",false))
                        item["ever_visible"] = bool(original.get("ever_visible",false))
                        break
    return restored

## Append a complete source/rest take into the one immutable stream FIFO.
## The renderer provides authenticated source windows and measured glyph
## context. Nothing else can allocate source serials or publish a partial
## admitted owner.
func append_take(facts: StreamGeometry, windows: Array[Vector2], source_beat: float,
        start_world: float, take_key: String, empty_strip: bool,
        first_header_spaces: float, rest_gap: float, guided: bool = false,
        display_context: bool = false, leading_rest_beats: float = 0.0) -> void:
    last_admitted = -1
    var first_serial: int = serial+1
    var original_origin: float = start_world-source_beat
    var hidden: bool = take_key == "prepared"
    if windows.is_empty():
        return
    var density: float = maxf(1.0,facts.density)
    var gap_pixels: float = facts.gap
    var duration: float = facts.duration
    var width: float = facts.width
    # Limit every visible strip to the selected practice window. The
    # pre-engraved atlas may include neighboring bars for authentic clefs,
    # ties and safe cut geometry; those bars are not part of this lesson.
    # Previous/next exercises must enter only through their own admitted
    # source strips, never through an expanded context crop.
    var context: bool = false
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
            "clip_floor":minf(bounds.x,facts.display_start) if is_first and context else bounds.x,
            "clip_ceiling":maxf(bounds.y,facts.display_end) if is_last and context else bounds.y,
            "clip_leading_spaces":leading_spaces,
            "clip_trailing_spaces":2.2 if is_last else 0.0,
            "piece_duration":duration,"take_key":take_key,
            "pending":take_key == "prepared" or guided,
            "hidden_until_armed":hidden}]
        if is_first and leading_rest_beats > .0001:
            # The same immutable take owns both its preparation rest and
            # its source. The header follows the complete written bar.
            specs.push_front({
                "kind":"rest","rest_position":"before",
                "owner_serial":strip_serial,"take_owner":first_serial,
                "world_origin":start_world-leading_spaces*gap_pixels/density-leading_rest_beats,
                "source_floor":0.0,"source_ceiling":leading_rest_beats,
                "take_key":"rest","pending":false,
                "hidden_until_armed":hidden})
        if is_last and rest_gap > .0001 and not (context and facts.display_end > duration+.0001):
            # The REST occupies the count-in bar in musical time. Its
            # retained *ink*, however, must finish before the next opening's
            # clef/key header, which appears immediately BEFORE the new
            # first attack. A full-bar REST clip left no physical slot for
            # that header at the fixed one-bar automatic deadline and
            # stranded genuine MIDI repeats in permanent 'admitting'.
            #
            # This is a visual clip budget, not a second transport clock:
            # the rest glyph still represents the complete measure, while
            # the rightmost part of its staff is reserved for the incoming
            # native header. The queue still rejects any actual ink overlap.
            var header_beats: float = first_header_spaces*gap_pixels/density
            var printed_rest: float = maxf(0.0,
                rest_gap-header_beats-Admission.OFFSCREEN_MARGIN_BEATS)
            if printed_rest > .0001:
                specs.append({
                    "kind":"rest","owner_serial":strip_serial,
                    "take_owner":first_serial,
                    "world_origin":original_origin+duration,
                    "source_floor":0.0,"source_ceiling":printed_rest,
                    "take_key":"rest","pending":false,
                    "hidden_until_armed":hidden})
        if not queue.enqueue(canvas(),specs,
                _pool.repeat_segments,_pool.rest_segments,
                _pool.first_once,facts.world,width,
                facts.playhead,density,gap_pixels,
                duration,empty_strip,_pool.allocate,timeline_placement):
            # Do not leave a partial, ungraded take after a failed append.
            if added > 0:
                queue.withdraw_take_tail(canvas(),first_serial,
                    facts.world,density,gap_pixels,duration,width,
                    facts.playhead,"failed_take_batch")
                if queue.has_take(first_serial):
                    push_error("Cannot safely roll back incomplete streamed take")
            push_error("Refused immutable score strip %d: %s (world=%.5f source=%.5f..%.5f start=%.5f)" % [
                strip_serial,queue.admission_refusal,facts.world,
                bounds.x,bounds.y,start_world])
            return
        added += 1
    serial = first_serial+windows.size()-1
    _binding.admitted(first_serial)
    last_admitted = first_serial

## Single transport reservation authority for Play, Resume, Retry, and
## pre-ACK paused source reuse. A view exposes only source geometry.
## A successful immutable admission is reported using exactly the
## controller's committed queue generation and measured source geometry.
## This receipt is sent unchanged to the Python playback coordinator.
func receipt(planned: Dictionary, admitted: Dictionary, world: float,
        opening: float, header_spaces: float, density: float, gap: float,
        duration: float, current_world: float, right: float,
        bpm: float) -> Dictionary:
    if admitted.is_empty():
        return {}
    var entry_beats: float = float(admitted["start_world"])-opening+ \
        Admission.clip_bounds({
            "kind":"source","source_floor":opening,
            "source_ceiling":duration,
            "clip_floor":opening,"clip_ceiling":duration,
            "clip_leading_spaces":header_spaces,
        },density,gap,duration).x/maxf(1.0,density) - \
        current_world-right
    var entry_seconds: float = Admission.lead_seconds(
        entry_beats,0.0,bpm)
    var receipt_data: Dictionary = {
        "action":str(planned["action"]),
        "mode":str(planned["mode"]),
        "start_world":float(admitted["start_world"]),
        "source_opening":opening,"at_world":world,
        "lead_seconds":Admission.lead_seconds(
            float(admitted["start_world"]),world,bpm),
        "first_ink_delay_seconds":entry_seconds,
        "online_strips":queue.online.size(),
    }
    if OS.get_environment("PIANO_TEACHER_TIMING_DIAGNOSTICS") == "1":
        print("SCORE_TRANSPORT_RECEIPT:",JSON.stringify(receipt_data))
    admitted["admission_receipt"] = receipt_data
    return admitted

func reject_candidate(facts: StreamGeometry, owner_serial: int, before_serial: int,
        old_live_serial: int, snapshot: Dictionary) -> void:
    # A failed pre-commit reservation must not leave a speculative future
    # source/rest pair occupying the musical axis.
    if owner_serial > before_serial:
        queue.withdraw_take_tail(canvas(),owner_serial,facts.world,
            facts.density,facts.gap,facts.duration,
            facts.width,facts.playhead,"rejected_admission")
    elif not snapshot.is_empty():
        StreamLifecycle.restore_owner(queue.online,owner_serial,snapshot)
    _binding.restore_live(old_live_serial)

func arm_take(facts: StreamGeometry, opening: float, start_world: float,
        leading_rest_beats: float = 0.0) -> Dictionary:
    return _binding.arm(facts,serial,allocate_source.bind(false,leading_rest_beats),
        reject_candidate,cancel_arm,opening,start_world)

## Append the take the musical timeline placed at `start_world`. Python
## chose that place after all ink still ahead; unseen leftovers go first.
func place_timeline_take(facts: StreamGeometry, opening: float,
        start_world: float, right: float, header: float,
        count_in_beats: float) -> Dictionary:
    # The exposure rule applies to every take, including unplayed takes.
    if not facts.ready or not is_finite(start_world) or start_world <= facts.world:
        return {}
    var windows: Array[Vector2] = _source_windows.call(maxf(0.0,opening))
    if windows.is_empty():
        return {}
    var plan: Dictionary = queue.preview_tail_withdrawal(facts.world,facts.density,
        facts.gap,facts.duration,facts.width,facts.playhead,-1,false,-1,null,true)
    # Refuse an impossible published location before withdrawing anything.
    # Use the exact opening window and same local/peer geometry as enqueue.
    var first: Vector2 = windows[0]
    var leading_spaces: float = facts.first_header_spaces if first.x <= .0001 else 1.6
    var first_left: float = start_world-opening+first.x-leading_spaces*facts.gap/maxf(1.0,facts.density)
    var occupied: float = queue.occupied_end(plan["remaining"],facts.density,facts.gap,facts.duration)
    var inside: bool = facts.playhead+(first_left-facts.world)*facts.density <= facts.width
    if first_left < occupied-.00001 or not queue.clears_prior_layers(
            first_left,facts.density,facts.width,facts.playhead,inside):
        return {}
    var result: Dictionary = queue.apply_withdrawal(canvas(),plan,"timeline_replaces_unseen")
    if not result["removed"].is_empty():
        _binding.reconcile()
    if not bool(result["complete"]):
        return {}
    # Use the actual committed retained prefix, not a second preview.
    var before: float = maxf(facts.world,_ink_end(facts,queue.online))
    var leading_rest: float = clampf(start_world-header-before-
        Admission.REST_GAP_BEATS,0.0,count_in_beats)
    timeline_placement = true
    var admitted: Dictionary = arm_take(facts,opening,start_world,
        leading_rest if leading_rest >= .5 else 0.0)
    timeline_placement = false
    return admitted

## A forecast is not permission to publish source ink. Retain this
## compatibility entry point as a fail-closed boundary.
func place_predicted_take(_facts: StreamGeometry, _opening: float,
        _start_world: float) -> int:
    return -1

func adopt_predicted_take(facts: StreamGeometry, owner_serial: int,
        opening: float) -> Dictionary:
    return _binding.adopt(facts,owner_serial,opening)

func withdraw_predicted_take(facts: StreamGeometry, owner_serial: int) -> void:
    if not queue.withdraw_take_tail(canvas(),owner_serial,facts.world,
            facts.density,facts.gap,facts.duration,facts.width,
            facts.playhead,"prediction_not_taken").is_empty():
        _binding.reconcile()

## World beat where the ink that cannot be withdrawn ends (this layer and
## live peer layers), or -INF when the staff ahead is empty.
func ink_end(facts: StreamGeometry) -> float:
    var remaining: Array = queue.preview_timed_withdrawal(facts.world,
        facts.density,facts.gap,facts.duration,facts.width,facts.playhead)
    return _ink_end(facts,remaining)

func _ink_end(facts: StreamGeometry, remaining: Array) -> float:
    var end: float = queue.occupied_end(remaining,facts.density,facts.gap,facts.duration)
    var peer: float = queue.minimum_peer_opening(facts.density,facts.width,facts.playhead)
    if is_finite(peer):
        end = maxf(end,peer)
    return end

func allocate_source(facts: StreamGeometry, source_beat: float, start_world: float,
        from_beat: float, take_key: String, empty_strip: bool,
        display_context: bool = false, leading_rest_beats: float = 0.0) -> int:
    var before: int = serial
    append_source(facts,source_beat,start_world,from_beat,take_key,empty_strip,false,display_context,leading_rest_beats)
    return last_admitted if serial > before else -1

func free_opening(facts: StreamGeometry, right: float, header: float) -> float:
    var preview: Dictionary = queue.preview_tail_withdrawal(
        facts.world,facts.density,facts.gap,facts.duration,facts.width,facts.playhead)
    return float(RecoveryPlanner.free_slot(queue,facts,preview["remaining"],right,header)["start"])

func schedule_recovery(facts: StreamGeometry, world: float, source_opening: float,
        graded_deadline_world: float, right: float, header: float,
        plan_id: String = "",
        allow_count_in: bool = false, count_in_beats: float = 0.0,
        deadline_at_or_after: bool = false, untimed: bool = false,
        presentation_take: String = "") -> bool:
    var prepared: Dictionary = _recovery.prepare(queue,facts,source_opening,
        graded_deadline_world,right,header,plan_id,allow_count_in,
        count_in_beats,deadline_at_or_after,untimed)
    if prepared.is_empty():
        return false
    if bool(prepared.get("already_admitted",false)):
        return true
    var saved_suffix: Array = prepared["saved_suffix"]
    var checked: float = float(prepared["start"])
    var on_empty: bool = bool(prepared["empty"])
    var prior_live: int = _binding.live_owner()
    var withdrawal: Dictionary = queue.apply_withdrawal(canvas(),prepared["withdrawal"],"recovery_replan")
    if not withdrawal["removed"].is_empty():
        _binding.reconcile()
    if not bool(withdrawal["complete"]) or queue.online.size() != int(prepared["remaining_count"]):
        # The archive may refuse one of several suffix withdrawals after
        # earlier owners were already removed. Restore ONLY the missing
        # original tail; re-enqueueing the still-online survivors would
        # duplicate their immutable notes and fail recovery altogether.
        var still_present: int = maxi(0,
            queue.online.size()-int(prepared["remaining_count"]))
        push_error("RECOVERY_TRANSACTION: tail withdrawal incomplete")
        restore_future_suffix(facts,saved_suffix.slice(still_present),
            facts.world)
        _binding.restore_live(prior_live)
        return false
    var before: int = self.serial
    # Only GuidedPresentationSession invokes this path with its published
    # Free plan ID. This printed source is never eligible for graded reuse;
    # Play/Resume/Retry must reserve and acknowledge their own timed owner.
    append_source(facts,source_opening,checked,source_opening,
        presentation_take if not presentation_take.is_empty() else
            "guided:"+str(prepared["identity"]),on_empty,true)
    _binding.restore_live(prior_live)
    if self.serial > before:
        _recovery.record(str(prepared["identity"]),last_admitted,checked,
            facts.world,on_empty)
        return true
    # If a retained segment/asset failed halfway through its measure batch,
    # eliminate that exact unexposed newly allocated owner first. Its serial
    # was not committed by _stream_add_take; the pre-existing suffix retains
    # the only authoritatively valid music at its original world positions.
    var partial_owner: int = before+1
    if queue.has_take(partial_owner):
        queue.withdraw_take_tail(canvas(),partial_owner,
            facts.world,facts.density,facts.gap,
            facts.duration,facts.width,facts.playhead,
            "recovery_incomplete_append")
    if queue.has_take(partial_owner):
        push_error("RECOVERY_TRANSACTION: incomplete take cannot be rolled back")
        return false
    restore_future_suffix(facts,saved_suffix,facts.world)
    _binding.restore_live(prior_live)
    return false

## Projection receives the live FIFO only inside its authoritative owner.
func paint(painter, canvas: CanvasItem, pool) -> void:
    if painter.paint_staff(canvas,queue.online):
        painter.project_stream(queue.online,pool.all_segments,
            painter.size.x*painter.PLAYHEAD_FRACTION)
        if pool.annotations != null:
            pool.annotations.queue_redraw()
        painter.paint_diagnostics(canvas)

func offline_snapshot() -> Array:
    return queue.offline

func visible_take_keys() -> Array:
    var keys: Array = []
    for item in queue.online:
        if str(item.get("kind","source")) == "source":
            keys.append(str(item.get("take_key","")))
    return keys

func first_strip_origin_after(from_world: float) -> float:
    var result := INF
    for item in queue.online:
        var origin: float = float(item["world_origin"])
        if origin >= from_world:
            result = minf(result,origin)
    return result

func invalidate_retained() -> void:
    _pool.invalidate(canvas(),queue.online)

func attach_compiled() -> void:
    _pool.attach_compiled(queue.online)

func bind_segment(segment_id: String) -> bool:
    return _binding.bind_segment(segment_id)

func acknowledge_arm() -> bool:
    return _binding.acknowledge_arm()

func observe_state(facts: StreamGeometry, state: Dictionary, graded_beat: float,
        allow_admission: bool) -> void:
    _binding.observe_state(facts,state,graded_beat,allow_admission,trim,cancel_arm)
    # Sounding evidence remains distinct from physical ink exposure;
    # only the exposure-safe queue may withdraw an unseen suffix.
    var live: int = _binding.live_owner()
    if live >= 0 and not bool(state.get("paused",false)):
        queue.mark_sounded(live,facts.world)

func unscored_take_status() -> String:
    return _binding.unscored_take

func scheduled_plan_opening(identity: String) -> float:
    return _recovery.opening(identity)
