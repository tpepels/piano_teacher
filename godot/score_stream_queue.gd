extends RefCounted
## One online FIFO of immutable retained passages, and one offline FIFO of
## immutable source plans. Only the head of online may expire. Only the
## unexposed, unacknowledged suffix may be withdrawn. The offline ledger
## preserves every plan ever queued or withdrawn, including its exact
## authored source/rest geometry and the reason for withdrawal.
##
## The CanvasItem pool is an implementation detail of StreamLifecycle.
## Ownership of queue order lives exclusively here.
const Admission := preload("res://score_stream_admission.gd")
const Lifecycle := preload("res://notation/native/stream_lifecycle.gd")

var online: Array = []
var offline: Array = []

static func owner_id(item: Dictionary) -> int:
    return int(item.get("owner_serial",abs(int(item.get("serial",0)))))

static func _record(item: Dictionary) -> Dictionary:
    # A source plan is plain JSON-compatible metadata; never archive Nodes,
    # clipping controls, CanvasItem resources or mutable draw buffers.
    return {
        "kind":str(item.get("kind","source")),
        "owner_serial":owner_id(item),
        "world_origin":float(item["world_origin"]),
        "source_floor":float(item["source_floor"]),
        "source_ceiling":float(item["source_ceiling"]),
        "take_key":str(item.get("take_key","")),
        "slot_id":str(item.get("slot_id","")),
    }

func enqueue(owner: Control, specs: Array, source_pool: Array,
        rest_pool: Array, first_source: Node2D, world: float,
        viewport_width: float, playhead_x: float,
        density: float, gap: float, source_duration: float) -> bool:
    if specs.is_empty() or str(specs[0].get("kind","")) != "source":
        return false
    var planned: Dictionary = specs[0]
    var opening_left: float = float(planned.get("world_origin",NAN)) + \
        Admission.clip_bounds(planned,density,gap,source_duration).x / density
    # A new passage must be completely outside the viewport, and behind
    # everything already physically written into the online queue.
    if not is_finite(opening_left) or \
            playhead_x + (opening_left-world)*density <= viewport_width:
        return false
    if not online.is_empty():
        var end_beat := -INF
        for item in online:
            var bounds: Vector2 = Admission.clip_bounds(
                item,density,gap,source_duration)
            end_beat = maxf(end_beat,float(item["world_origin"])+bounds.y/density)
        if opening_left < end_beat-.00001:
            return false
    if not Lifecycle._admit(owner,online,specs,
            source_pool,rest_pool,first_source):
        return false
    var frozen: Array = []
    for item in specs:
        frozen.append(_record(item))
    offline.append({"owner_serial":owner_id(online[-1]),
        "plan":frozen,"event":"enqueued"})
    return true

func _is_safe_tail(owner_serial: int, world: float, density: float,
        gap: float, duration: float, viewport_width: float,
        playhead_x: float, force_unacknowledged: bool) -> bool:
    var found := false
    var source: Dictionary = {}
    for index in range(online.size()-1,-1,-1):
        var item: Dictionary = online[index]
        if owner_id(item) != owner_serial:
            break
        found = true
        if bool(item.get("ever_visible",false)):
            return false
        if str(item.get("kind","")) == "source":
            source = item
        if not bool(item.get("hidden_until_armed",false)):
            # Even a rejected provisional control cannot retract ink that
            # might already be visible before the next render callback.
            var bounds: Vector2 = Admission.clip_bounds(
                item,density,gap,duration)
            var first_x: float = playhead_x + \
                (float(item["world_origin"])-world)*density+bounds.x
            if first_x <= viewport_width:
                return false
    return found and not source.is_empty() and (
        force_unacknowledged or (
        bool(source.get("pending",false)) and
        not bool(source.get("armed",false))))

func withdraw_tail(owner: Control, world: float, density: float,
        gap: float, duration: float, viewport_width: float,
        playhead_x: float, reason: String,
        force_unacknowledged: bool = false) -> Array[int]:
    # The only permitted right-end dequeue operation. A visible/acknowledged
    # prefix is NEVER changed, even when future musical decisions differ.
    var withdrawn: Array[int] = []
    while not online.is_empty():
        var last_owner: int = owner_id(online[-1])
        if not _is_safe_tail(last_owner,world,density,gap,duration,
                viewport_width,playhead_x,force_unacknowledged):
            break
        var snapshot: Array = []
        while not online.is_empty() and owner_id(online[-1]) == last_owner:
            var item: Dictionary = online.pop_back()
            snapshot.push_front(_record(item))
            withdrawn.append(int(item.get("serial",0)))
            Lifecycle.retire(owner,item)
        offline.append({"owner_serial":last_owner,
            "plan":snapshot,"event":"withdrawn","reason":reason})
        # Explicit abort removes only its own last owner. It must never
        # silently delete another reserved passage behind that owner.
        if force_unacknowledged:
            break
    return withdrawn

func expire_front(owner: Control, world: float, density: float,
        gap: float, duration: float, playhead_x: float) -> Array[int]:
    var removed: Array[int] = []
    var corrupt_owners: Dictionary = {}
    for entry in online:
        if str(entry.get("kind","source")) != "source":
            continue
        var source = entry.get("segment")
        var source_clip = entry.get("clip")
        if source == null or not is_instance_valid(source) or \
                source_clip == null or not is_instance_valid(source_clip):
            corrupt_owners[owner_id(entry)] = true
    # Work exclusively from the head. A corrupt source marks its paired
    # rest for removal, but neither may bypass a preceding visible entry.
    while not online.is_empty():
        var item: Dictionary = online[0]
        var segment = item.get("segment")
        var clip = item.get("clip")
        var invalid: bool = corrupt_owners.has(owner_id(item)) or \
            segment == null or not is_instance_valid(segment) or \
            clip == null or not is_instance_valid(clip)
        if not invalid and not Lifecycle.expired(
                item,world,density,playhead_x,gap,duration):
            break
        removed.append(int(item.get("serial",0)))
        offline.append({"owner_serial":owner_id(item),
            "plan":[_record(item)],"event":"expired" if not invalid else "invalid"})
        Lifecycle.retire(owner,item)
        online.pop_front()
    return removed

func reset(owner: Control) -> void:
    # Whole-score teardown is the only operation that may clear all online
    # entries irrespective of visibility. Keep the offline history intact.
    while not online.is_empty():
        var item: Dictionary = online.pop_front()
        offline.append({"owner_serial":owner_id(item),
            "plan":[_record(item)],"event":"score_reset"})
        Lifecycle.retire(owner,item)

func exposed_owner(owner_serial: int) -> bool:
    for item in online:
        if owner_id(item) == owner_serial and bool(item.get("ever_visible",false)):
            return true
    return false
