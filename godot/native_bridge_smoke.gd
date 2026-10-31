extends SceneTree
## Developer/CI preflight. Godot and the CPython engine must both load before
## the application opens; a blank library is not an acceptable fallback.
const LIBRARY := "res://native/piano_bridge.gdextension"
const MAX_MS := 12000

var engine: Object
var started_ms := 0
var request_id := -1

func _initialize() -> void:
    started_ms = Time.get_ticks_msec()
    if not FileAccess.file_exists(LIBRARY):
        _fail("Missing GDExtension manifest at " + LIBRARY)
        return
    if not ClassDB.class_exists("PianoNative"):
        var result: int = GDExtensionManager.load_extension(LIBRARY)
        print("PIANO_NATIVE_LOAD_STATUS=", result)
    if not ClassDB.class_exists("PianoNative"):
        _fail("Godot has not registered PianoNative. Check earlier loader and libpython messages.")
        return
    engine = ClassDB.instantiate("PianoNative")
    if engine == null:
        _fail("Registered PianoNative could not be constructed")
        return
    print("PIANO_NATIVE_CLASS_OK")

func _process(_delta: float) -> bool:
    if engine == null:
        return true
    if Time.get_ticks_msec() - started_ms > MAX_MS:
        var detail: String = str(engine.call("failure_message"))
        _fail("Native Python engine timeout" +
            (": " + detail if not detail.is_empty() else ""))
        return true
    var error: String = str(engine.call("failure_message"))
    if not error.is_empty():
        _fail("Embedded Python failed: " + error)
        return true
    if not bool(engine.call("is_ready")):
        return false
    if request_id < 0:
        request_id = int(engine.call("submit", "GET", "/library", ""))
        if request_id < 0:
            _fail("Python engine ready but library request rejected")
        return false
    for response in engine.call("take_responses"):
        if not response is Dictionary or int(response.get("id", -1)) != request_id:
            continue
        var status: int = int(response.get("status", 0))
        var data: PackedByteArray = response.get("body", PackedByteArray())
        var parsed: Variant = JSON.parse_string(data.get_string_from_utf8())
        if status != 200 or not parsed is Dictionary or not parsed.has("pieces"):
            _fail("In-process /library failed (%d): %s" % [
                status, data.get_string_from_utf8().left(500)])
            return true
        print("PIANO_NATIVE_LIBRARY_OK pieces=", (parsed["pieces"] as Array).size())
        quit(0)
        return true
    return false

func _fail(message: String) -> void:
    printerr("PIANO_NATIVE_STARTUP_FAILED: " + message)
    quit(1)
