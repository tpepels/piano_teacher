extends RefCounted
## Sole owner of retained stream CanvasItem staging, positioning and retirement.
## The native view decides WHAT to admit; this module owns HOW a source/rest
## segment enters and leaves the one moving world coordinate system.
##
## A newly allocated (or invalidated) segment MUST compile while attached to
## its visible owner. Putting an uncompiled segment inside an invisible clip
## prevents Godot from recording its draw commands and silently loses ink.
const Admission := preload("res://score_stream_admission.gd")
const STAGING_X := -1000000.0
const EXIT_MARGIN_PIXELS := 60.0

static func _offstage(segment: Node2D) -> void:
    segment.position = Vector2(STAGING_X,0.0)

# Each attempt owns one source slot and, when the score has an authored
# gap, one rest slot. These slots are never independently inserted.
static func admit(owner: Control, passes: Array, specs: Array,
        source_pool: Array, rest_pool: Array, first_source: Node2D) -> bool:
    var used: Dictionary = {}
    var identities: Dictionary = {}
    for item in passes:
        var existing: String = str(item.get("slot_id",
            "%d:%s" % [int(item.get("owner_serial",abs(int(item.get("serial",0))))),
                str(item.get("kind","source"))]))
        if identities.has(existing):
            return false
        identities[existing] = true
        if item.has("segment"):
            used[item["segment"]] = true
    # Every admission is one complete passage: exactly one source and
    # zero or one dependent rest. A rest-only insertion is forbidden.
    if specs.is_empty():
        return false
    var batch_owner: int = int(specs[0].get("owner_serial",0))
    var has_source := false
    # Preflight identity collisions before creating ANY CanvasItem.
    for spec in specs:
        var role: String = str(spec.get("kind",""))
        var owner_serial: int = int(spec.get("owner_serial",0))
        if role not in ["source","rest"] or owner_serial <= 0 or \
                owner_serial != batch_owner:
            return false
        if role == "source":
            has_source = true
        var identifier: String = "%d:%s" % [owner_serial,role]
        if identities.has(identifier):
            return false
        identities[identifier] = true
    if not has_source:
        return false
    for spec in specs:
        var role: String = str(spec["kind"])
        var pool: Array = source_pool if role == "source" else rest_pool
        var choice: Node2D = null
        if role == "source" and first_source != null and \
                is_instance_valid(first_source) and not used.has(first_source):
            choice = first_source
        if choice == null:
            for segment in pool:
                if segment != null and is_instance_valid(segment) and \
                        not used.has(segment):
                    choice = segment
                    break
        if choice == null:
            # Overflow always uses the same lifecycle and pre-compilation
            # contract, regardless of whether the content is notes or rests.
            choice = owner._new_retained_segment(role)
            pool.append(choice)
        used[choice] = true
        var owner_serial: int = int(spec["owner_serial"])
        var serial: int = owner_serial if role == "source" else -owner_serial
        passes.append(_create(owner,choice,role,
            float(spec["world_origin"]),float(spec["source_floor"]),
            float(spec["source_ceiling"]),str(spec["take_key"]),serial,
            bool(spec.get("pending",false)),owner_serial,
            bool(spec.get("hidden_until_armed",false))))
    return true


static func reposition(passes: Array, owner_serial: int,
        new_origin: float) -> bool:
    # Only a never-published READY reservation may be repositioned. Its
    # dependent written rest gets exactly the same world-axis translation.
    if not is_finite(new_origin):
        return false
    var source: Dictionary = {}
    for item in passes:
        if int(item.get("owner_serial",abs(int(item.get("serial",0))))) == \
                owner_serial and str(item.get("kind","source")) == "source":
            source = item
            break
    if source.is_empty() or str(source.get("take_key","")) != "prepared" or \
            not bool(source.get("pending",false)) or \
            bool(source.get("armed",false)):
        return false
    var previous: float = float(source["world_origin"])
    if new_origin < previous-.00001:
        return false
    var movement: float = new_origin-previous
    for item in passes:
        if int(item.get("owner_serial",abs(int(item.get("serial",0))))) == owner_serial:
            if not bool(item.get("hidden_until_armed",false)):
                return false
    for item in passes:
        if int(item.get("owner_serial",abs(int(item.get("serial",0))))) == owner_serial:
            item["world_origin"] = float(item["world_origin"])+movement
    return true


static func activate(passes: Array, owner_serial: int, key: String,
        armed: bool) -> bool:
    # One source may bind to each backend transport identity. The paired
    # semantic rest gets published in the same atomic transition.
    if owner_serial <= 0 or key.is_empty():
        return false
    var target: Dictionary = {}
    for item in passes:
        if str(item.get("kind","source")) != "source":
            continue
        if int(item.get("owner_serial",abs(int(item.get("serial",0))))) == owner_serial:
            target = item
        elif str(item.get("take_key","")) == key and \
                not bool(item.get("pending",false)):
            return false
    if target.is_empty():
        return false
    for item in passes:
        if int(item.get("owner_serial",abs(int(item.get("serial",0))))) != owner_serial:
            continue
        item["hidden_until_armed"] = false
        if str(item.get("kind","source")) == "source":
            item["take_key"] = key
            item["pending"] = false
            item["armed"] = armed
    return true


static func widen_source(passes: Array, owner_serial: int,
        floor: float, ceiling: float) -> bool:
    # A claimed automatic copy can clip previous events, and a running
    # copy can enlarge its future window. Both use the same role identity.
    for item in passes:
        if int(item.get("owner_serial",abs(int(item.get("serial",0))))) != \
                owner_serial or str(item.get("kind","source")) != "source":
            continue
        item["source_floor"] = maxf(float(item["source_floor"]),floor)
        item["source_ceiling"] = maxf(float(item["source_ceiling"]),ceiling)
        return true
    return false


static func screen_bounds(item: Dictionary, density: float,
        gap: float, score_duration: float) -> Vector2:
    # Identical rightmost-ink calculation governs presentation and expiry.
    # Rest ink and source ink have different contours, but NO separate
    # placement or removal algorithms.
    if str(item.get("kind","source")) == "rest":
        return Vector2(0.0,float(item["source_ceiling"])*density)
    return Admission.engraved_clip_bounds(
        float(item["source_floor"]),float(item["source_ceiling"]),
        density,gap,score_duration)


static func _create(owner: Control, segment: Node2D, kind: String,
        world_origin: float, source_floor: float, source_ceiling: float,
        take_key: String, serial: int, pending: bool,
        owner_serial: int = 0, hidden_until_armed: bool = false) -> Dictionary:
    assert(is_instance_valid(owner) and is_instance_valid(segment))
    assert(kind in ["source","rest"])
    var clip := Control.new()
    clip.name = "StreamPassWindow" if kind == "source" else "StreamSemanticRest"
    clip.visible = false
    clip.clip_contents = true
    clip.mouse_filter = Control.MOUSE_FILTER_IGNORE
    clip.focus_mode = Control.FOCUS_NONE
    owner.add_child(clip)
    if bool(segment.get("compiled")):
        segment.visible = false
        segment.reparent(clip,false)
    else:
        # Keep the segment in the owner's visible Canvas tree until _draw()
        # produces its retained commands. The empty clip is never published.
        if segment.get_parent() != owner:
            segment.reparent(owner,false)
        _offstage(segment)
        segment.visible = true
    return {"segment":segment,"clip":clip,
        "world_origin":world_origin,
        "source_floor":source_floor,"source_ceiling":source_ceiling,
        "take_key":take_key,"pending":pending,
        "serial":serial,"kind":kind,
        "owner_serial":owner_serial if owner_serial > 0 else abs(serial),
        "slot_id":"%d:%s" % [
            owner_serial if owner_serial > 0 else abs(serial),kind],
        "hidden_until_armed":hidden_until_armed}

static func prepare_recompile(owner: Control, passes: Array) -> void:
    # A viewport/hand change invalidates both source and printed rest ink.
    # Detach from hidden clips before queuing a new draw; reattach atomically
    # on the frame where the rebuilt segment is confirmed compiled.
    for item in passes:
        var segment = item.get("segment")
        var clip = item.get("clip")
        if segment == null or not is_instance_valid(segment):
            continue
        if clip != null and is_instance_valid(clip):
            clip.visible = false
        if segment.get_parent() != owner:
            segment.reparent(owner,false)
        _offstage(segment)
        segment.visible = true

static func attach_compiled(passes: Array) -> void:
    # Scene-tree changes belong to the frame coordinator, never _draw().
    # Only completed retained buffers are allowed into their presentation
    # clips; the next projection frame positions the clip before revealing.
    for item in passes:
        var segment = item.get("segment")
        var clip = item.get("clip")
        if segment == null or not is_instance_valid(segment) or \
                clip == null or not is_instance_valid(clip) or \
                not bool(segment.get("compiled")):
            continue
        if segment.get_parent() != clip:
            segment.visible = false
            segment.reparent(clip,false)
            clip.visible = false

static func project(item: Dictionary, world: float, playhead_x: float,
        density: float, staff_gap: float, viewport: Vector2,
        score_duration: float) -> bool:
    var segment = item.get("segment")
    var clip = item.get("clip")
    if segment == null or not is_instance_valid(segment) or \
            clip == null or not is_instance_valid(clip):
        return false
    if not bool(segment.get("compiled")):
        clip.visible = false
        # A fresh segment is still attached to its owner to compile; a
        # recompiled one is detached by prepare_recompile().
        return false
    if bool(item.get("hidden_until_armed",false)) and \
            not bool(item.get("armed",false)):
        clip.visible = false
        return false
    var bounds: Vector2 = screen_bounds(
        item,density,staff_gap,score_duration)
    var position: float = playhead_x + \
        (float(item["world_origin"])-world)*density
    # Reparenting is forbidden during CanvasItem._draw(). The frame owner
    # attached a fully compiled source earlier, or it remains hidden.
    if segment.get_parent() != clip:
        clip.visible = false
        return false
    clip.position = Vector2(position+bounds.x,0.0)
    clip.size = Vector2(maxf(1.0,bounds.y-bounds.x),viewport.y)
    segment.position = Vector2(-bounds.x,0.0)
    segment.visible = true
    clip.visible = true
    return true

static func retire(owner: Control, item: Dictionary) -> void:
    # One symmetric release path for expired, invalid and reset passages.
    # Both source and semantic rest CanvasItems remain precompiled in the
    # owner's reusable pool; only their presentation windows are destroyed.
    var segment = item.get("segment")
    var clip = item.get("clip")
    if clip != null and is_instance_valid(clip):
        clip.visible = false
    if segment != null and is_instance_valid(segment):
        segment.visible = false
        if segment.get_parent() != owner:
            segment.reparent(owner,false)
        _offstage(segment)
    if clip != null and is_instance_valid(clip):
        clip.queue_free()

static func release_all(owner: Control, passes: Array) -> void:
    for item in passes:
        retire(owner,item)
    passes.clear()

static func expired(item: Dictionary, world: float, density: float,
        playhead_x: float, staff_gap: float, score_duration: float) -> bool:
    var right: float = screen_bounds(
        item,density,staff_gap,score_duration).y
    var origin_x: float = playhead_x + \
        (float(item["world_origin"])-world)*density
    return origin_x+right < -EXIT_MARGIN_PIXELS

static func prune(owner: Control, passes: Array, world: float, density: float,
        playhead_x: float, staff_gap: float, score_duration: float) -> Array[int]:
    var removed: Array[int] = []
    # If a source CanvasItem or clip has been invalidated externally, its
    # dependent rest is also invalid. Normal expiration is independent:
    # source ink may leave earlier than its authentic printed rest.
    var invalid_owners: Dictionary = {}
    for item in passes:
        if str(item.get("kind","source")) != "source":
            continue
        var segment = item.get("segment")
        var clip = item.get("clip")
        if segment == null or not is_instance_valid(segment) or \
                clip == null or not is_instance_valid(clip):
            invalid_owners[int(item.get("owner_serial",
                abs(int(item.get("serial",0)))))] = true
    for index in range(passes.size()-1,-1,-1):
        var item: Dictionary = passes[index]
        var segment = item.get("segment")
        var clip = item.get("clip")
        var owner_serial: int = int(item.get("owner_serial",
            abs(int(item.get("serial",0)))))
        var invalid: bool = invalid_owners.has(owner_serial) or \
            segment == null or not is_instance_valid(segment) or \
            clip == null or not is_instance_valid(clip)
        if not invalid and not expired(item,world,density,playhead_x,
                staff_gap,score_duration):
            continue
        removed.append(int(item.get("serial",0)))
        retire(owner,item)
        passes.remove_at(index)
    return removed
