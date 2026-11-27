extends RefCounted
## Detached worker job: immutable inputs, exclusively owned CPU resources.
## No Node, CanvasItem, GPU texture, viewport or session is touched here.
const NativeScoreAssets := preload("res://native_score_assets.gd")
const Timeline := preload("res://notation/shared/timeline.gd")
const Engraving := preload("res://notation/native/score_engraving.gd")
const Geometry := preload("res://notation/native/geometry.gd")
const Spacing := preload("res://notation/shared/spacing_policy.gd")
const LivingScore := preload("res://living_score.gd")

var body: PackedByteArray
var request: Dictionary
var viewport: Vector2
var density: float
var result: Dictionary = {}
var _cancel_lock := Mutex.new()
var _cancelled := false

func cancel() -> void:
    _cancel_lock.lock()
    _cancelled = true
    _cancel_lock.unlock()


func _should_stop() -> bool:
    _cancel_lock.lock()
    var cancelled: bool = _cancelled
    _cancel_lock.unlock()
    return cancelled

func _init(bytes: PackedByteArray, identity: Dictionary,
        viewport_size: Vector2, configured_density: float) -> void:
    body = bytes
    request = identity.duplicate(true)
    viewport = viewport_size
    density = configured_density

func _decode_bundle() -> Dictionary:
    var document := JSON.new()
    if document.parse(body.get_string_from_utf8()) != OK or not document.data is Dictionary:
        result = {"invalid_bundle":true,
            "error":"Practice engine returned no source-bound score bundle"}
        return {}
    return document.data

func _validated_axis(bundle: Dictionary):
    var problem: String = NativeScoreAssets.bundle_error(bundle,{
        "fingerprint":request["fingerprint"],"revision":request["revision"],
        "hand":request["hand"],"stage_key":request["stage_key"]})
    if not problem.is_empty():
        result = {"invalid_bundle":true,"error":problem}
        return null
    var model: Dictionary = bundle["model"]
    problem = Geometry.supported(model)
    if not problem.is_empty():
        result = {"invalid_bundle":true,"error":problem}
        return null
    var axis := Timeline.new()
    if not axis.load_model(model):
        result = {"invalid_bundle":true,"error":axis.last_error}
        return null
    return axis

func _prepare_atlas(engraving, layout: Dictionary) -> bool:
    if not NativeScoreAssets.prepare_engraving(engraving,layout):
        result = {"invalid_bundle":true,"error":engraving.failure_reason}
        return false
    if _should_stop():
        return false
    engraving.glyphs.prepare_head_interiors()
    return not _should_stop()

func refit(viewport_size: Vector2, configured_density: float) -> void:
    viewport = viewport_size
    density = configured_density

func _fit(engraving) -> bool:
    if engraving.prepare(density,viewport,Spacing.PLAYHEAD_FRACTION):
        return not _should_stop()
    result = {"invalid_bundle":engraving.incomplete_assets,"error":engraving.failure_reason}
    return false

func run() -> void:
    if _should_stop():
        return
    if result.has("engraving"):
        # A superseded viewport can reuse the same CPU atlas. This only runs
        # before the first upload, so no GPU texture crosses into the pool.
        var started: int = Time.get_ticks_usec()
        if _fit(result["engraving"]):
            var elapsed: float = float(Time.get_ticks_usec()-started)*.001
            result["timing"]["geometry_cpu_ms"] += elapsed
            result["timing"]["total_ms"] += elapsed
        return
    # If a malformed nested value aborts a typed Godot loader, this request
    # still rejects the bundle and the supervisor can issue one fresh replay.
    result = {"invalid_bundle":true,"error":"Score bundle contains malformed notation data"}
    var started: int = Time.get_ticks_usec()
    var bundle: Dictionary = _decode_bundle()
    if bundle.is_empty() or _should_stop():
        return
    var decoded: int = Time.get_ticks_usec()
    var axis = _validated_axis(bundle)
    if axis == null or _should_stop():
        return
    var validated: int = Time.get_ticks_usec()
    var engraving := Engraving.new(axis)
    if not _prepare_atlas(engraving,bundle["layout"]):
        return
    var atlas_at: int = Time.get_ticks_usec()
    if not _fit(engraving):
        return
    # The main thread receives the sole owner after the pool task joins.
    engraving.glyphs.begin_upload()
    var layout: Dictionary = bundle["layout"]
    result = {"engraving":engraving,"attacks":layout["attack_map"],
        "source_groups":LivingScore.prepare(layout),
        "timing":{"revision":request["revision"],"bytes":body.size(),
            "decode_ms":float(decoded-started)*.001,
            "validate_ms":float(validated-decoded)*.001,
            "atlas_cpu_ms":float(atlas_at-validated)*.001,
            "geometry_cpu_ms":float(Time.get_ticks_usec()-atlas_at)*.001,
            "total_ms":float(Time.get_ticks_usec()-started)*.001}}
