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
static func validate_batch(passes: Array, specs: Array) -> bool:
    var identities: Dictionary = {}
    for item in passes:
        var existing: String = str(item.get("slot_id",
            "%d:%s" % [int(item.get("owner_serial",abs(int(item.get("serial",0))))),
                str(item.get("kind","source"))]))
        if identities.has(existing):
            return false
        identities[existing] = true
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
    var source_spec: Dictionary = {}
    var rest_spec: Dictionary = {}
    for spec in specs:
        var origin: float = float(spec.get("world_origin",NAN))
        var floor: float = float(spec.get("source_floor",NAN))
        var ceiling: float = float(spec.get("source_ceiling",NAN))
        if not is_finite(origin) or not is_finite(floor) or \
                not is_finite(ceiling) or floor < 0.0 or ceiling <= floor:
            return false
        if str(spec["kind"]) == "source":
            source_spec = spec
        else:
            rest_spec = spec
    var source_length: float = float(source_spec.get("piece_duration",
        source_spec["source_ceiling"]))
    # The source window cannot extend beyond its own declared passage.
    # Otherwise the paired rest begins while source ink is still musical
    # content, defeating chronological FIFO admission.
    if not is_finite(source_length) or source_length <= 0.0 or \
            float(source_spec["source_ceiling"]) > source_length+.00001:
        return false
    if not rest_spec.is_empty():
        if absf(float(rest_spec["world_origin"])-(
                float(source_spec["world_origin"])+source_length)) > .00001:
            # Even though source and rest use separate retained CanvasItems,
            # their relative musical position is controlled by ONE batch.
            return false
    return true


static func _admit(owner: Control, passes: Array, specs: Array,
        source_pool: Array, rest_pool: Array, first_source: Node2D) -> bool:
    if not validate_batch(passes,specs):
        return false
    var used: Dictionary = {}
    for item in passes:
        if item.has("segment"):
            used[item["segment"]] = true
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
        var placed: Dictionary = _create(owner,choice,role,
            float(spec["world_origin"]),float(spec["source_floor"]),
            float(spec["source_ceiling"]),str(spec["take_key"]),serial,
            bool(spec.get("pending",false)),owner_serial,
            bool(spec.get("hidden_until_armed",false)))
        placed["take_owner"] = int(spec.get("take_owner",owner_serial))
        if spec.has("clip_floor") and spec.has("clip_ceiling"):
            placed["clip_floor"] = float(spec["clip_floor"])
            placed["clip_ceiling"] = float(spec["clip_ceiling"])
            placed["clip_leading_spaces"] = float(
                spec.get("clip_leading_spaces",0.0))
            placed["clip_trailing_spaces"] = float(
                spec.get("clip_trailing_spaces",0.0))
        passes.append(placed)
    return true


static func snapshot_owner(passes: Array, owner_serial: int) -> Dictionary:
    # Snapshot the entire logical take, including all measure strips.
    # A rejected Play must never leave a later strip armed.
    var result: Dictionary = {}
    for item in passes:
        if int(item.get("take_owner",item.get("owner_serial",0))) != owner_serial:
            continue
        result[str(item["slot_id"])] = {
            "take_key":item.get("take_key",""),
            "pending":item.get("pending",false),
            "armed":item.get("armed",false),
            "hidden_until_armed":item.get("hidden_until_armed",false)}
    return result


static func restore_owner(passes: Array, owner_serial: int,
        snapshot: Dictionary) -> bool:
    if snapshot.is_empty():
        return false
    var found := false
    for item in passes:
        if int(item.get("take_owner",item.get("owner_serial",0))) != owner_serial:
            continue
        found = true
        if not snapshot.has(str(item["slot_id"])):
            return false
    if not found:
        return false
    for item in passes:
        if int(item.get("take_owner",item.get("owner_serial",0))) != owner_serial:
            continue
        var original: Dictionary = snapshot[str(item["slot_id"])]
        for field in original:
            item[field] = original[field]
    return true


static func activate(passes: Array, owner_serial: int, key: String,
        armed: bool) -> bool:
    # One engine transport binds all immutable strips of its selected take.
    # Source/geometry never change; only provisional transport state does.
    if owner_serial <= 0 or key.is_empty():
        return false
    var target: Dictionary = {}
    for item in passes:
        if str(item.get("kind","source")) == "source" and \
                int(item.get("take_owner",item.get("owner_serial",0))) == owner_serial:
            target = item
            break
    if target.is_empty():
        return false
    var target_floor: float = float(target.get("source_floor",-INF))
    for item in passes:
        if str(item.get("kind","source")) != "source" or \
                int(item.get("take_owner",item.get("owner_serial",0))) == owner_serial:
            continue
        if str(item.get("take_key","")) == key and \
                not bool(item.get("pending",false)) and \
                absf(float(item.get("source_floor",-INF))-target_floor) < .00001:
            return false
    for item in passes:
        if int(item.get("take_owner",item.get("owner_serial",0))) != owner_serial:
            continue
        item["hidden_until_armed"] = false
        if str(item.get("kind","source")) == "source":
            item["take_key"] = key
            item["pending"] = false
            item["armed"] = armed
    return true


static func screen_bounds(item: Dictionary, density: float,
        gap: float, score_duration: float) -> Vector2:
    # Admission and retirement use this same canonical printed geometry.
    return Admission.clip_bounds(item,density,gap,score_duration)


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

static func present_pool(segments: Array, used: Dictionary = {}) -> void:
    # The view never sets source/rest CanvasItem position or visibility.
    # Keep uncompiled buffers visible to Godot but stage them far offscreen;
    # hide compiled buffers that currently have no projected clip owner.
    for segment in segments:
        if segment == null or not is_instance_valid(segment):
            continue
        var should_show: bool = used.has(segment) or not bool(segment.get("compiled"))
        if segment.visible != should_show:
            segment.visible = should_show
        if not bool(segment.get("compiled")):
            _offstage(segment)


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
    # This flag is monotonic. Once any authentic glyph of a queue entry
    # reaches the viewport, its owner can never be removed from the tail.
    if clip.position.x < viewport.x and \
            clip.position.x+clip.size.x > 0.0:
        item["ever_visible"] = true
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

static func expired(item: Dictionary, world: float, density: float,
        playhead_x: float, staff_gap: float, score_duration: float) -> bool:
    var right: float = screen_bounds(
        item,density,staff_gap,score_duration).y
    var origin_x: float = playhead_x + \
        (float(item["world_origin"])-world)*density
    return origin_x+right < -EXIT_MARGIN_PIXELS
