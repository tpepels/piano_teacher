extends RefCounted
## Detached worker job: immutable inputs, exclusively owned CPU resources.
## No Node, CanvasItem, GPU texture, viewport or session is touched here.
const NativeScoreAssets := preload("res://native_score_assets.gd")
const Timeline := preload("res://notation/shared/timeline.gd")
const Engraving := preload("res://notation/native/score_engraving.gd")
const Geometry := preload("res://notation/native/geometry.gd")
const Spacing := preload("res://notation/shared/spacing_policy.gd")

var body: PackedByteArray
var request: Dictionary
var viewport: Vector2
var density: float
var result: Dictionary = {}

func _init(bytes: PackedByteArray, identity: Dictionary,
        viewport_size: Vector2, configured_density: float) -> void:
    body = bytes
    request = identity.duplicate(true)
    viewport = viewport_size
    density = configured_density

func run() -> void:
    var started: int = Time.get_ticks_usec()
    var document := JSON.new()
    if document.parse(body.get_string_from_utf8()) != OK or not document.data is Dictionary:
        result = {"error":"Practice engine returned no source-bound score bundle"}
        return
    var bundle: Dictionary = document.data
    var decoded: int = Time.get_ticks_usec()
    var problem: String = NativeScoreAssets.bundle_error(bundle,{
        "fingerprint":request["fingerprint"],"revision":request["revision"],
        "hand":request["hand"],"stage_key":request["stage_key"]})
    if not problem.is_empty():
        result = {"error":problem}
        return
    var model: Dictionary = bundle["model"]
    problem = Geometry.supported(model)
    if not problem.is_empty():
        result = {"error":problem}
        return
    var axis := Timeline.new()
    if not axis.load_model(model):
        result = {"error":axis.last_error}
        return
    var validated: int = Time.get_ticks_usec()
    var engraving := Engraving.new(axis)
    engraving.glyphs.begin_cpu_preparation()
    if not NativeScoreAssets.prepare_engraving(engraving,bundle["layout"]):
        result = {"error":engraving.failure_reason}
        return
    engraving.glyphs.prepare_head_interiors()
    var atlas_at: int = Time.get_ticks_usec()
    if not engraving.prepare(density,viewport,Spacing.PLAYHEAD_FRACTION):
        result = {"error":engraving.failure_reason}
        return
    # The main thread receives the sole owner after the pool task joins.
    result = {"engraving":engraving,"layout":NativeScoreAssets.compact_layout(bundle["layout"]),
        "timing":{"revision":request["revision"],"bytes":body.size(),
            "decode_ms":float(decoded-started)*.001,
            "validate_ms":float(validated-decoded)*.001,
            "atlas_cpu_ms":float(atlas_at-validated)*.001,
            "geometry_cpu_ms":float(Time.get_ticks_usec()-atlas_at)*.001,
            "total_ms":float(Time.get_ticks_usec()-started)*.001}}
