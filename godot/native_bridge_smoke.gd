extends SceneTree
## Real embedded-CPython/GDExtension smoke. Default checks the native catalog.
## CI's opt-in real-score path exercises engraving, semantic score, ack and
## practice transport with a generated two-hand MIDI rather than an empty shelf.
const LIBRARY := "res://native/piano_bridge.gdextension"
const FIXTURE := "phase6_native_fixture.mid"
const MAX_STARTUP_MS := 12000
const MAX_REAL_SCORE_MS := 120000

var engine: Object
var started_ms := 0
var request_id := -1
var operation := ""
var real_score := false
var revision := -1
var started_transport := -1

func _initialize() -> void:
    started_ms = Time.get_ticks_msec()
    real_score = OS.get_environment("PIANO_NATIVE_REAL_SCORE_SMOKE") == "1"
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

func _submit(next_operation: String, payload: Dictionary = {}) -> void:
    operation = next_operation
    request_id = int(engine.call("submit",next_operation,JSON.stringify(payload)))
    if request_id < 0:
        _fail("Native engine rejected " + next_operation)

func _process(_delta: float) -> bool:
    if engine == null:
        return true
    var deadline_ms := MAX_REAL_SCORE_MS if real_score else MAX_STARTUP_MS
    if Time.get_ticks_msec() - started_ms > deadline_ms:
        var detail: String = str(engine.call("failure_message"))
        _fail("Native Python engine timeout in " + operation +
            (": " + detail if not detail.is_empty() else ""))
        return true
    var error: String = str(engine.call("failure_message"))
    if not error.is_empty():
        _fail("Embedded Python failed: " + error)
        return true
    if not bool(engine.call("is_ready")):
        return false
    if request_id < 0:
        _submit("library.catalog")
        return false
    for response in engine.call("take_responses"):
        if not response is Dictionary or int(response.get("id",-1)) != request_id:
            continue
        var status: int = int(response.get("status",3))
        var data: PackedByteArray = response.get("body",PackedByteArray())
        var parsed: Variant = JSON.parse_string(data.get_string_from_utf8())
        if status != 0 or not parsed is Dictionary:
            _fail("In-process %s failed (%d): %s" % [
                operation,status,data.get_string_from_utf8().left(500)])
            return true
        var values: Dictionary = parsed
        match operation:
            "library.catalog":
                if not values.has("pieces"):
                    _fail("Native library catalog omitted pieces")
                    return true
                print("PIANO_NATIVE_LIBRARY_OK pieces=", (values["pieces"] as Array).size())
                if not real_score:
                    quit(0)
                    return true
                var found := false
                for raw in values["pieces"]:
                    if raw is Dictionary and str(raw.get("id","")) == FIXTURE:
                        found = true
                if not found:
                    _fail("Generated real-score fixture absent from embedded library")
                    return true
                _submit("library.open",{"id":FIXTURE})
            "library.open":
                revision = int(values.get("revision",-1))
                if not bool(values.get("loaded",false)) or revision < 0:
                    _fail("MIDI opened without loaded state and revision")
                    return true
                print("PIANO_NATIVE_MIDI_OPEN_OK revision=",revision)
                _submit("score.native_layout")
            "score.native_layout":
                if int(values.get("revision",-1)) != revision or \
                        not values.has("anchors") or \
                        not values["anchors"] is Dictionary or \
                        values["anchors"].is_empty():
                    _fail("Actual Verovio note coordinates missing or stale")
                    return true
                print("PIANO_NATIVE_SCORE_GEOMETRY_OK anchors=",
                    values["anchors"].size())
                _submit("score.semantic")
            "score.semantic":
                if int(values.get("revision",-1)) != revision or \
                        not values.has("notes") or \
                        not values["notes"] is Array or \
                        values["notes"].is_empty():
                    _fail("Semantic score has missing notes or wrong revision")
                    return true
                print("PIANO_NATIVE_SEMANTIC_OK notes=",values["notes"].size())
                _submit("practice.command",{"action":"score_ready","revision":revision})
                operation = "practice.ack"
            "practice.ack":
                if not bool(values.get("loaded",false)) or \
                        str(values.get("phase","")) == "loading":
                    _fail("Score-ready acknowledgement did not release loading")
                    return true
                _submit("practice.command",{"action":"start"})
                operation = "practice.start"
            "practice.start":
                if not bool(values.get("running",false)) or \
                        str(values.get("phase","")) != "count_in":
                    _fail("Real MIDI lesson did not enter count-in")
                    return true
                started_transport = int(values.get("transport_id",-1))
                _submit("practice.command",{"action":"pause"})
                operation = "practice.pause"
            "practice.pause":
                if not bool(values.get("paused",false)):
                    _fail("Native practice pause did not stop transport")
                    return true
                _submit("practice.command",{"action":"resume"})
                operation = "practice.resume"
            "practice.resume":
                if not bool(values.get("running",false)) or \
                        bool(values.get("paused",false)) or \
                        int(values.get("transport_id",-1)) != started_transport:
                    _fail("Resume must retain the real MIDI attempt")
                    return true
                print("PIANO_NATIVE_REAL_SCORE_WORKFLOW_OK revision=",revision)
                quit(0)
                return true
            _:
                _fail("Unexpected native smoke operation: " + operation)
                return true
        return false
    return false

func _fail(message: String) -> void:
    printerr("PIANO_NATIVE_STARTUP_FAILED: " + message)
    quit(1)
