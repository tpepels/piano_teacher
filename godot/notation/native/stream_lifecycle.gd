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

static func create(owner: Control, segment: Node2D, kind: String,
        world_origin: float, source_floor: float, source_ceiling: float,
        take_key: String, serial: int, pending: bool) -> Dictionary:
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
        "serial":serial,"kind":kind}

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
    if str(item.get("kind","source")) == "source" and \
            str(item.get("take_key","")) == "prepared" and \
            bool(item.get("pending",false)) and \
            not bool(item.get("armed",false)):
        clip.visible = false
        return false
    var is_rest: bool = str(item.get("kind","source")) == "rest"
    var bounds: Vector2 = (Vector2(0.0,
        float(item["source_ceiling"])*density)
        if is_rest else Admission.engraved_clip_bounds(
            float(item["source_floor"]),float(item["source_ceiling"]),
            density,staff_gap,score_duration))
    var position: float = playhead_x + \
        (float(item["world_origin"])-world)*density
    # The parent clip is positioned BEFORE the compiled segment is exposed.
    if segment.get_parent() != clip:
        segment.visible = false
        segment.reparent(clip,false)
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
    var is_rest: bool = str(item.get("kind","source")) == "rest"
    var right: float = (float(item["source_ceiling"])*density
        if is_rest else Admission.engraved_clip_bounds(
            float(item["source_floor"]),float(item["source_ceiling"]),
            density,staff_gap,score_duration).y)
    var origin_x: float = playhead_x + \
        (float(item["world_origin"])-world)*density
    return origin_x+right < -EXIT_MARGIN_PIXELS

static func prune(owner: Control, passes: Array, world: float, density: float,
        playhead_x: float, staff_gap: float, score_duration: float) -> Array[int]:
    var removed: Array[int] = []
    for index in range(passes.size()-1,-1,-1):
        var item: Dictionary = passes[index]
        var segment = item.get("segment")
        var clip = item.get("clip")
        var invalid: bool = segment == null or not is_instance_valid(segment) or \
            clip == null or not is_instance_valid(clip)
        if not invalid and not expired(item,world,density,playhead_x,
                staff_gap,score_duration):
            continue
        removed.append(int(item.get("serial",0)))
        retire(owner,item)
        passes.remove_at(index)
    return removed
