extends SceneTree
## Real GDExtension + embedded CPython: a cold score engraving runs on the
## asset worker, so the command/tick worker keeps answering while it runs.
const LIBRARY := "res://native/piano_bridge.gdextension"

var engine: Object
var fixture := ""
var phase := "catalog"
var request_id := -1
var layout_id := -1
var layout_started_ms := 0
var snapshots_during_layout := 0
var snapshot_id := -1
var revision := -1
var started_ms := 0

func _initialize() -> void:
    started_ms = Time.get_ticks_msec()
    fixture = OS.get_cmdline_user_args()[0]
    if not ClassDB.class_exists("PianoNative"):
        GDExtensionManager.load_extension(LIBRARY)
    engine = ClassDB.instantiate("PianoNative")

func _submit(operation: String, payload: Dictionary = {}) -> int:
    return int(engine.call("submit",operation,JSON.stringify(payload)))

func _finish(code: int, message: String) -> void:
    print(message)
    engine = null
    quit(code)

func _process(_delta: float) -> bool:
    if engine == null:
        return true
    if Time.get_ticks_msec()-started_ms > 120000:
        _finish(1,"NATIVE_ASSET_WORKER_FAILED: timeout in " + phase)
        return true
    if not bool(engine.call("is_ready")):
        var error: String = str(engine.call("failure_message"))
        if not error.is_empty():
            _finish(1,"NATIVE_ASSET_WORKER_FAILED: " + error)
        return false
    if request_id < 0 and phase == "catalog":
        request_id = _submit("library.catalog")
    # Keep exactly one state read in flight while the engraving runs.
    if phase == "layout" and snapshot_id < 0:
        snapshot_id = _submit("state.snapshot")
    for response in engine.call("take_responses"):
        var id: int = int(response.get("id",-1))
        var body: PackedByteArray = response.get("body",PackedByteArray())
        var values: Variant = JSON.parse_string(body.get_string_from_utf8())
        if int(response.get("status",3)) != 0 or not values is Dictionary:
            _finish(1,"NATIVE_ASSET_WORKER_FAILED: %s -> %s" % [
                phase,body.get_string_from_utf8().left(300)])
            return true
        if id == request_id and phase == "catalog":
            phase = "open"
            request_id = _submit("library.open",{"id":fixture})
        elif id == request_id and phase == "open":
            revision = int(values.get("revision",-1))
            phase = "layout"
            layout_started_ms = Time.get_ticks_msec()
            layout_id = _submit("score.native_layout")
        elif id == snapshot_id:
            snapshot_id = -1
            if phase == "layout":
                snapshots_during_layout += 1
        elif id == layout_id:
            var elapsed: int = Time.get_ticks_msec()-layout_started_ms
            var ok: bool = int(values.get("revision",-1)) == revision and \
                values.get("anchors") is Array and not values["anchors"].is_empty()
            _finish(0 if ok else 1,
                "NATIVE_ASSET_WORKER layout_ms=%d snapshots_during_layout=%d anchors_ok=%s" % [
                    elapsed,snapshots_during_layout,str(ok)])
            return true
    return false
