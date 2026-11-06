extends RefCounted
## Sole online FIFO owner. The separate offline FIFO holds withdrawn musical
## source plans, and its append-only checked journal survives score reopening.
## Committed positions are write-once; removal is allowed at the HEAD for
## expired ink, or the maximal safe unexposed speculative TAIL.
const Admission := preload("res://score_stream_admission.gd")
const Lifecycle := preload("res://notation/native/stream_lifecycle.gd")
const Archive := preload("res://score_stream_archive.gd")

# A lesson transition can briefly keep two NativeViews alive for the
# SAME musical source. Share one journal writer/sequence in that process.
# Weak references do not retain histories after their last renderer exits.
static var _shared_archives: Dictionary = {}

var online: Array = []
# Source owner serials belong to ONE renderer; another renderer can also
# have serial 1. A stable per-renderer journal scope prevents collisions.
var _writer_id := ""

func _init() -> void:
    _writer_id = str(get_instance_id())

var _archive = Archive.new()
var offline: Array:
    get:
        return _archive.pending.duplicate(true)
var history: Array:
    get:
        return _archive.history.duplicate(true)
var last_error: String:
    get:
        return _archive.last_error

func bind_score(score_key: String, directory: String = Archive.DEFAULT_DIR,
        independent_recovery: bool = false) -> bool:
    if not online.is_empty():
        return false
    if independent_recovery:
        # Only independent process/restart tests bypass the live shared
        # archive. Production readers must always use the single writer.
        _archive = Archive.new()
        return _archive.bind_score(score_key,directory)
    var identity: String = directory.path_join(score_key.sha256_text())
    var weak: Variant = _shared_archives.get(identity)
    if weak is WeakRef:
        var shared = weak.get_ref()
        if shared != null and shared.last_error.is_empty():
            _archive = shared
            return true
    var next = Archive.new()
    if not next.bind_score(score_key,directory):
        _archive = next
        return false
    _archive = next
    _shared_archives[identity] = weakref(next)
    return true

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
        "piece_duration":float(item.get("piece_duration",
            item.get("source_ceiling",0.0))),
        "take_key":str(item.get("take_key","")),
        "slot_id":str(item.get("slot_id","")),
        "take_owner":int(item.get("take_owner",owner_id(item))),
        "clip_floor":float(item.get("clip_floor",NAN)),
        "clip_ceiling":float(item.get("clip_ceiling",NAN)),
    }

func enqueue(owner: Control, specs: Array, source_pool: Array,
        rest_pool: Array, first_source: Node2D, world: float,
        viewport_width: float, playhead_x: float,
        density: float, gap: float, source_duration: float) -> bool:
    # Validate the caller's ORIGINAL musical request before considering
    # an offline template. A malformed rest or overlapping source cannot be
    # silently repaired by a compatible archived passage.
    if specs.is_empty() or str(specs[0].get("kind","")) != "source" or \
            not Lifecycle.validate_batch(online,specs):
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
    var prepared: Array = specs
    var matching: Dictionary = _archive.compatible(specs)
    if not matching.is_empty():
        # Materialize exact archived source content only after the admission
        # boundary has already approved the new world-time location.
        prepared = _archive.materialize(matching,specs)
        if prepared.is_empty():
            return false
    var before: int = online.size()
    if not Lifecycle._admit(owner,online,prepared,
            source_pool,rest_pool,first_source):
        return false
    var plan: Array = []
    for item in prepared:
        plan.append(_record(item))
    for index in range(prepared.size()):
        online[before+index]["piece_duration"] = float(
            prepared[index].get("piece_duration",source_duration))
    var id: int = int(matching.get("id",0))
    if not _archive.record("enqueued",int(prepared[0]["owner_serial"]),
            plan,"offline_reuse" if id > 0 else "new",id,
            _writer_id):
        # An unjournaled passage must not become live or consume its
        # preceding offline copy. Roll back its entire newly created suffix.
        while online.size() > before:
            Lifecycle.retire(owner,online.pop_back())
        return false
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
    # Once a strip is still entirely unexposed it may be retracted,
    # even if an earlier strip of the same graded attempt was acknowledged.
    # That is the essential difference between per-measure strips and an
    # immutable full-passage owner that wrongly locks its invisible suffix.
    return found and not source.is_empty()

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
        for i in range(online.size()-1,-1,-1):
            if owner_id(online[i]) != last_owner:
                break
            snapshot.push_front(_record(online[i]))
        # Journal BEFORE releasing graphics or removing an entry. The
        # complete source/rest pair can then be recovered after a crash.
        if not _archive.record("withdrawn",last_owner,snapshot,reason,0,
                _writer_id):
            return withdrawn
        while not online.is_empty() and owner_id(online[-1]) == last_owner:
            var item: Dictionary = online.pop_back()
            withdrawn.append(int(item.get("serial",0)))
            Lifecycle.retire(owner,item)
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
        var last_of_owner: bool = (online.size() == 1 or
            owner_id(online[1]) != owner_id(item))
        if last_of_owner and not _archive.record("completed",
                owner_id(item),[_record(item)],
                "invalid" if invalid else "expired",0,
                _writer_id):
            break
        removed.append(int(item.get("serial",0)))
        Lifecycle.retire(owner,item)
        online.pop_front()
    return removed

func reset(owner: Control) -> void:
    # Score teardown archives each complete owner BEFORE freeing its clips.
    # The offline FIFO remains available when this source is reopened.
    while not online.is_empty():
        var first_owner: int = owner_id(online[0])
        var specs: Array = []
        for item in online:
            if owner_id(item) != first_owner:
                break
            specs.append(_record(item))
        # The archived ORIGINAL batch can contain more slots than remain
        # online (e.g. the source has expired but its rest is still visible).
        # Preserve the complete batch without popping non-existent entries
        # or consuming the first slot of the NEXT owner.
        var remaining_count: int = specs.size()
        var complete: Array = _archive.original_plan(
            first_owner,_writer_id)
        if not complete.is_empty():
            specs = complete
        if not _archive.record("score_reset",first_owner,specs,
                "score_unload",0,_writer_id):
            push_error("Score plan preservation failed: "+last_error)
            return
        for i in range(remaining_count):
            Lifecycle.retire(owner,online.pop_front())

func has_take(take_serial: int) -> bool:
    for item in online:
        if int(item.get("take_owner",owner_id(item))) == take_serial:
            return true
    return false

func exposed_owner(owner_serial: int) -> bool:
    for item in online:
        if owner_id(item) == owner_serial and bool(item.get("ever_visible",false)):
            return true
    return false
