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
var admission_refusal := ""

func _reject_admission(reason: String) -> bool:
    # Keep the first physical reason on this queue; renderer diagnostics
    # report it together with the immutable source and world coordinates.
    admission_refusal = reason
    return false

# Source owner serials belong to ONE renderer; another renderer can also
# have serial 1. A stable per-renderer journal scope prevents collisions.
var _writer_id := ""
# Existing lesson layers remain independent CanvasItem owners, but they
# share one physical screen. Weak peer references enforce global admission
# against every still-live outgoing layer (including rapid lesson changes).
var _peer_views: Array[WeakRef] = []

func register_peer(view: Control) -> void:
    if view == null or not is_instance_valid(view):
        return
    for ref in _peer_views:
        if ref.get_ref() == view:
            return
    _peer_views.append(weakref(view))

# Clearance between outgoing and incoming ink, in pixels.
const PEER_MARGIN_PX := 60.0
# Printed rests already provide a whole-measure separation and a final
# barline. Keep a raster safety gap, not the source-to-source 60 px cushion.
const PEER_REST_MARGIN_PX := 6.0

func minimum_peer_opening(density: float,
        viewport_width: float, playhead_x: float,
        popping_in: bool = false, kinds: String = "all") -> float:
    # Earliest permitted world time for the first pixel of new ink.
    # READY can schedule beyond this barrier; an engine-authored exact
    # deadline must be rejected if it arrives earlier.
    var earliest := -INF
    for ref in _peer_views:
        var view = ref.get_ref()
        if view == null or not is_instance_valid(view) or \
                not view.has_method("stream_peer_clearance_facts"):
            continue
        # Peer data contains primitive, immutable physical geometry only.
        # Reading another renderer's _stream_queue is forbidden.
        var facts: Dictionary = view.stream_peer_clearance_facts()
        if facts.is_empty() or int(facts.get("queue_id",-1)) == get_instance_id():
            continue
        var peer_density: float = maxf(1.0,float(facts["density"]))
        var peer_playhead: float = float(facts["playhead_x"])
        for item in facts["ends"]:
            # kinds: "all", "source" (ink that blocks an empty-strip
            # opening) or "rest" (a written rest an opening may follow).
            var is_rest: bool = bool(item["rest"])
            if (kinds == "source" and is_rest) or (kinds == "rest" and not is_rest):
                continue
            var peer_end: float = float(item["end_world"])
            earliest = maxf(earliest,
                peer_popin_after(peer_end,peer_density,playhead_x,density,
                    PEER_REST_MARGIN_PX if is_rest else PEER_MARGIN_PX)
                if popping_in else peer_opening_after(peer_end,
                peer_density,peer_playhead,density,viewport_width,playhead_x))
    return earliest


static func peer_popin_after(peer_end: float, peer_density: float,
        playhead_x: float, density: float,
        margin_px: float = PEER_MARGIN_PX) -> float:
    # Ink that opens on the EMPTY strip (owner P5): the outgoing layer's last
    # pixel has passed the playhead. Ink of another density then never
    # overlaps it: a slower incoming layer only falls further behind, and a
    # faster one is still right of the old ink's last pixel when that pixel
    # leaves past the left edge (a pure linear bound on screen positions).
    var floor_beat: float = peer_end + margin_px/maxf(1.0,density)
    if density > peer_density:
        floor_beat += playhead_x*(density-peer_density)/(peer_density*density)
    return floor_beat


static func peer_opening_after(peer_end: float, peer_density: float,
        peer_playhead: float, density: float, viewport_width: float,
        playhead_x: float) -> float:
    # The earliest left edge of new ink after a peer layer's last printed
    # pixel at world beat peer_end. Equal densities may adjoin. Different
    # printed scales have different visual velocities: wait until the old
    # rightmost pixel has left the viewport before new ink enters.
    if absf(density-peer_density) < .0001:
        return peer_end
    return peer_end + (peer_playhead+PEER_MARGIN_PX)/peer_density + \
        (viewport_width-playhead_x)/density


func clears_prior_layers(opening_left: float, density: float,
        viewport_width: float, playhead_x: float,
        popping_in: bool = false) -> bool:
    return opening_left >= minimum_peer_opening(
        density,viewport_width,playhead_x,popping_in)-.00001


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

static func source_record(item: Dictionary) -> Dictionary:
    # A source plan is plain JSON-compatible metadata; never archive Nodes,
    # clipping controls, CanvasItem resources or mutable draw buffers.
    var stored: Dictionary = {
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
    }
    if item.has("rest_position"):
        stored["rest_position"] = str(item["rest_position"])
    if item.has("clip_floor") and item.has("clip_ceiling"):
        stored["clip_floor"] = float(item["clip_floor"])
        stored["clip_ceiling"] = float(item["clip_ceiling"])
        stored["clip_leading_spaces"] = float(
            item.get("clip_leading_spaces",0.0))
        stored["clip_trailing_spaces"] = float(
            item.get("clip_trailing_spaces",0.0))
    return stored

func enqueue(owner: Control, specs: Array, source_pool: Array,
        rest_pool: Array, first_source: Node2D, world: float,
        viewport_width: float, playhead_x: float,
        density: float, gap: float, source_duration: float,
        empty_strip: bool = false, create_segment: Callable = Callable(),
        pop_in: bool = false) -> bool:
    # Validate the caller's ORIGINAL musical request before considering
    # an offline template. A malformed rest or overlapping source cannot be
    # silently repaired by a compatible archived passage.
    admission_refusal = ""
    if not Lifecycle.validate_batch(online,specs):
        return _reject_admission("invalid_or_duplicate_source_rest_batch")
    var planned: Dictionary = {}
    for spec in specs:
        if str(spec.get("kind","")) == "source":
            planned = spec
            break
    var opening_left: float = float(planned.get("world_origin",NAN)) + \
        Admission.clip_bounds(planned,density,gap,source_duration).x / density
    # A new passage must be completely outside the viewport, and behind
    # everything already physically written into the online queue. The one
    # exception is a user Play/Resume on an empty strip (owner decision
    # 2026-11-08): with no ink of another take right of the playhead, here
    # or in a live peer layer, its opening may appear on the empty staff.
    var take: int = int(planned.get("take_owner",planned.get("owner_serial",-1)))
    var onto_empty_strip: bool = empty_strip and \
        not Admission.ink_ahead_of(online,world,density,gap,
            source_duration,take) and \
        minimum_peer_opening(density,viewport_width,playhead_x,true,
            "source") <= world+.00001
    var inside: bool = is_finite(opening_left) and \
        playhead_x + (opening_left-world)*density <= viewport_width
    if not is_finite(opening_left):
        return _reject_admission("nonfinite_first_printed_pixel")
    # A take the musical timeline placed may appear on the visible staff:
    # its world start was chosen after all ink that was still ahead.
    if inside and not onto_empty_strip and not pop_in:
        return _reject_admission("source_ink_inside_viewport_without_empty_strip")
    if not clears_prior_layers(opening_left,density,
            viewport_width,playhead_x,inside and (onto_empty_strip or pop_in)):
        return _reject_admission("source_ink_overlaps_previous_renderer_layer")
    var batch_left: float = opening_left
    for spec in specs:
        if str(spec.get("rest_position","after")) == "before":
            batch_left = minf(batch_left,float(spec["world_origin"]))
    if batch_left < opening_left-.00001 and not clears_prior_layers(
            batch_left,density,viewport_width,playhead_x):
        return _reject_admission("leading_rest_overlaps_previous_renderer_layer")
    if not online.is_empty():
        var end_beat := -INF
        for item in online:
            var bounds: Vector2 = Admission.clip_bounds(
                item,density,gap,source_duration)
            end_beat = maxf(end_beat,float(item["world_origin"])+bounds.y/density)
        if batch_left < end_beat-.00001:
            return _reject_admission(
                "source_or_rest_overlap: incoming=%.6f previous_end=%.6f" % [
                    batch_left,end_beat])
    var prepared: Array = specs
    var matching: Dictionary = _archive.compatible(specs)
    if not matching.is_empty():
        # Materialize exact archived source content only after the admission
        # boundary has already approved the new world-time location.
        prepared = _archive.materialize(matching,specs)
        if prepared.is_empty():
            return _reject_admission("archived_source_plan_unavailable")
    var before: int = online.size()
    if not Lifecycle.admit(owner,online,prepared,
            source_pool,rest_pool,first_source,create_segment):
        return _reject_admission("retained_canvas_allocation_failed")
    var plan: Array = []
    for item in prepared:
        plan.append(source_record(item))
    for index in range(prepared.size()):
        online[before+index]["piece_duration"] = float(
            prepared[index].get("piece_duration",source_duration))
        # Runtime-only proof of future-only admission. This timestamp is the
        # forward world axis at commit; it does not change immutable music,
        # and must not be recycled from an archived source plan.
        online[before+index]["admitted_world"] = world
        online[before+index]["admitted_viewport_width"] = viewport_width
        online[before+index]["admitted_playhead_x"] = playhead_x
        online[before+index]["admitted_density"] = density
        online[before+index]["admitted_staff_gap"] = gap
        online[before+index]["admitted_on_empty_strip"] = inside
    var id: int = int(matching.get("id",0))
    if not _archive.record("enqueued",int(prepared[0]["owner_serial"]),
            plan,"offline_reuse" if id > 0 else "new",id,
            _writer_id):
        # An unjournaled passage must not become live or consume its
        # preceding offline copy. Roll back its entire newly created suffix.
        while online.size() > before:
            Lifecycle.retire(owner,online.pop_back())
        return _reject_admission("source_journal_write_failed: "+_archive.last_error)
    return true

func _is_safe_tail(passes: Array, owner_serial: int, world: float,
        density: float, gap: float, duration: float,
        viewport_width: float, playhead_x: float) -> bool:
    var found := false
    var source: Dictionary = {}
    for index in range(passes.size()-1,-1,-1):
        var item: Dictionary = passes[index]
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

# Takes that sounded: the playhead reached their first note while live.
var sounded: Dictionary = {}

static func _take_starts(passes: Array) -> Dictionary:
    var starts: Dictionary = {}
    for item in passes:
        if str(item.get("kind","source")) != "source":
            continue
        var take: int = int(item.get("take_owner",owner_id(item)))
        var at: float = float(item["world_origin"])+float(item.get("source_floor",0.0))
        starts[take] = minf(float(starts.get(take,INF)),at)
    return starts

func mark_sounded(take_owner: int, world: float) -> void:
    if sounded.has(take_owner):
        return
    # Only this owner matters. Avoid constructing a map of all take
    # openings on every count-in frame. Existence of any eligible source
    # start is equivalent to testing the minimum start for this owner.
    for item in online:
        if str(item.get("kind","source")) == "source" and \
                int(item.get("take_owner",owner_id(item))) == take_owner and \
                float(item["world_origin"])+float(item.get("source_floor",0.0)) <= world+.0001:
            sounded[take_owner] = true
            return

## Number of tail strips that belong to takes which never sounded (an
## exposure abandoned before it began). Free's ink counts as sounded once
## its first target reached the playhead.
func unplayed_tail_count(passes: Array, world: float) -> int:
    var starts: Dictionary = _take_starts(passes)
    var count := 0
    for index in range(passes.size()-1,-1,-1):
        var item: Dictionary = passes[index]
        var take: int = int(item.get("take_owner",owner_id(item)))
        if not starts.has(take) or sounded.has(take):
            break
        var guided: bool = str(item.get("take_key","")).begins_with("guided:") or \
            bool(item.get("pending",false)) and not str(item.get("take_key","")) in ["prepared","predicted"]
        if guided and float(starts[take]) <= world+.0001:
            break
        count += 1
    return count

## Withdraw unplayed takes at the tail, even when visible: a new run of
## timed music replaces an exposure that never sounded.
func abandon_unplayed(owner: Control, world: float, reason: String) -> Array[int]:
    var removed: Array[int] = []
    var count: int = unplayed_tail_count(online,world)
    while count > 0 and not online.is_empty():
        var serial: int = owner_id(online[-1])
        var snapshot: Array = []
        for i in range(online.size()-1,-1,-1):
            if owner_id(online[i]) != serial:
                break
            snapshot.push_front(source_record(online[i]))
        if not _archive.record("withdrawn",serial,snapshot,reason,0,_writer_id):
            break
        while count > 0 and not online.is_empty() and owner_id(online[-1]) == serial:
            var item: Dictionary = online.pop_back()
            removed.append(int(item.get("serial",0)))
            Lifecycle.retire(owner,item)
            count -= 1
    return removed

## Withdraw one take at the tail whose first note is still ahead of the
## playhead (a predicted repeat that did not happen), even when visible.
func abandon_owner(owner: Control, take_owner: int, world: float, reason: String) -> Array[int]:
    var removed: Array[int] = []
    var start := INF
    for item in online:
        if int(item.get("take_owner",owner_id(item))) == take_owner and \
                str(item.get("kind","source")) == "source":
            start = minf(start,float(item["world_origin"])+float(item.get("source_floor",0.0)))
    if not is_finite(start) or start <= world+.0001:
        return removed
    while not online.is_empty() and \
            int(online[-1].get("take_owner",owner_id(online[-1]))) == take_owner:
        var serial: int = owner_id(online[-1])
        var snapshot: Array = []
        for i in range(online.size()-1,-1,-1):
            if owner_id(online[i]) != serial:
                break
            snapshot.push_front(source_record(online[i]))
        if not _archive.record("withdrawn",serial,snapshot,reason,0,_writer_id):
            break
        while not online.is_empty() and owner_id(online[-1]) == serial:
            var item: Dictionary = online.pop_back()
            removed.append(int(item.get("serial",0)))
            Lifecycle.retire(owner,item)
    return removed

func preview_tail_withdrawal(world: float, density: float,
        gap: float, duration: float, viewport_width: float,
        playhead_x: float, protected_take: int = -1,
        just_one_owner: bool = false, protected_strip: int = -1,
        base: Variant = null) -> Dictionary:
    # Pure admission preview: the actual withdrawal and a preflight
    # reservation use IDENTICAL pixel-exposure and protected-owner rules.
    # No archive, scene tree, or live queue mutation occurs here.
    var remaining: Array = (base as Array).duplicate() if base is Array else online.duplicate()
    var owners: Array[int] = []
    while not remaining.is_empty():
        var tail: Dictionary = remaining[-1]
        if owner_id(tail) == protected_strip:
            break
        if protected_take >= 0 and int(tail.get(
                "take_owner",owner_id(tail))) == protected_take:
            break
        var owner_serial: int = owner_id(tail)
        if not _is_safe_tail(remaining,owner_serial,world,density,gap,
                duration,viewport_width,playhead_x):
            break
        owners.append(owner_serial)
        while not remaining.is_empty() and owner_id(remaining[-1]) == owner_serial:
            remaining.pop_back()
        if just_one_owner:
            break
    return {"remaining":remaining,"owners":owners}


func withdraw_tail(owner: Control, world: float, density: float,
        gap: float, duration: float, viewport_width: float,
        playhead_x: float, reason: String,
        force_unacknowledged: bool = false,
        protected_take: int = -1, protected_strip: int = -1) -> Array[int]:
    # The only permitted right-end dequeue operation. A visible/acknowledged
    # prefix is NEVER changed, even when future musical decisions differ.
    var withdrawn: Array[int] = []
    var preview: Dictionary = preview_tail_withdrawal(
        world,density,gap,duration,viewport_width,playhead_x,
        protected_take,force_unacknowledged,protected_strip)
    for serial in preview["owners"]:
        if online.is_empty() or owner_id(online[-1]) != int(serial):
            push_error("Queue tail changed between preflight and withdrawal")
            break
        var snapshot: Array = []
        for i in range(online.size()-1,-1,-1):
            if owner_id(online[i]) != int(serial):
                break
            snapshot.push_front(source_record(online[i]))
        if not _archive.record("withdrawn",int(serial),snapshot,reason,0,
                _writer_id):
            break
        while not online.is_empty() and owner_id(online[-1]) == int(serial):
            var item: Dictionary = online.pop_back()
            withdrawn.append(int(item.get("serial",0)))
            Lifecycle.retire(owner,item)
    return withdrawn

func withdraw_take_tail(owner: Control, take_owner: int, world: float,
        density: float, gap: float, duration: float,
        viewport_width: float, playhead_x: float, reason: String) -> Array[int]:
    # Undo one provisional take atomically with respect to unrelated takes:
    # even a failed command may withdraw only its own rightmost strips.
    var removed: Array[int] = []
    while not online.is_empty() and \
            int(online[-1].get("take_owner",owner_id(online[-1]))) == take_owner:
        var portion: Array[int] = withdraw_tail(owner,world,density,gap,
            duration,viewport_width,playhead_x,reason,true)
        if portion.is_empty():
            break
        removed.append_array(portion)
    return removed


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
                owner_id(item),[source_record(item)],
                "invalid" if invalid else "expired",0,
                _writer_id):
            break
        removed.append(int(item.get("serial",0)))
        Lifecycle.retire(owner,item)
        online.pop_front()
    return removed

func reset(owner: Control) -> bool:
    # Journal every complete owner before releasing ANY scene resources.
    # A failed append leaves the entire online score and its binding intact.
    # The archive latches write failures, so no archived prefix can be reused
    # while its original physical source remains online after that failure.
    var batches: Array = []
    var cursor := 0
    while cursor < online.size():
        var first_owner: int = owner_id(online[cursor])
        var specs: Array = []
        while cursor < online.size() and owner_id(online[cursor]) == first_owner:
            specs.append(source_record(online[cursor]))
            cursor += 1
        # A remaining written rest still preserves its original source batch.
        var complete: Array = _archive.original_plan(first_owner,_writer_id)
        batches.append({"owner":first_owner,
            "plan":complete if not complete.is_empty() else specs})
    for batch in batches:
        if not _archive.record("score_reset",int(batch["owner"]),batch["plan"],
                "score_unload",0,_writer_id):
            push_error("Score plan preservation failed: "+last_error)
            return false
    while not online.is_empty():
        Lifecycle.retire(owner,online.pop_front())
    sounded.clear()
    return true

func has_take(take_serial: int) -> bool:
    for item in online:
        if int(item.get("take_owner",owner_id(item))) == take_serial:
            return true
    return false

static func source_identity(candidate: Dictionary) -> String:
    # The journal is keyed by immutable MUSICAL SOURCE, not transient
    # backend revision or transport ID. Reopening the same actual score
    # can therefore recover its withdrawn material without mixing songs.
    var source: Dictionary = {}
    for key in ["schema","duration_beats","sounding_duration_beats","notes",
            "display_notes","display_extent","display_measures","active_note_ids","notation_events",
            "measures","time_signatures","key_signatures","clefs",
            "beam_groups","tie_groups","slur_pairs","tuplets",
            "tempo_changes","hand"]:
        if candidate.has(key):
            source[key] = candidate[key]
    return JSON.stringify(source).sha256_text()
