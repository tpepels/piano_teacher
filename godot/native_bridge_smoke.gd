extends SceneTree
## Real embedded-CPython/GDExtension smoke. Default checks the native catalog.
## CI's opt-in real-score path exercises engraving, semantic score and
## source revision ACK with a generated two-hand MIDI rather than an empty shelf.
## Only the production Godot scene can physically authorize timed transport.
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
var fingerprint := ""
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
                fingerprint = str(values.get("piece_fingerprint",""))
                print("PIANO_NATIVE_MIDI_OPEN_OK revision=",revision)
                _submit("score.bundle",{"fingerprint":fingerprint,"revision":revision,
                    "stage_key":values["stage_key"],"hand":values["hand"],"generation":0})
            "score.bundle":
                var layout: Variant = values.get("layout")
                var model: Variant = values.get("model")
                var identifiers: Variant = values.get("source_note_ids")
                if (str(values.get("status","")) != "ready" or
                        int(values.get("revision",-1)) != revision or
                        str(values.get("fingerprint","")) != fingerprint or
                        not layout is Dictionary or not model is Dictionary or
                        not identifiers is Array or identifiers.is_empty() or
                        int(layout.get("revision",-1)) != revision or
                        int(model.get("revision",-1)) != revision or
                        not layout.get("anchors") is Array or
                        layout["anchors"].is_empty() or
                        not model.get("notes") is Array or
                        model["notes"].is_empty()):
                    _fail("Native ScoreBundle is missing original notes, engraving or source identity")
                    return true
                print("PIANO_NATIVE_SCORE_GEOMETRY_OK anchors=",
                    layout["anchors"].size())
                print("PIANO_NATIVE_SEMANTIC_OK notes=",model["notes"].size())
                _submit("practice.command",{"action":"score_ready","revision":revision})
                operation = "practice.ack"
            "practice.ack":
                # The in-process practice.command protocol separates its
                # accepted action from the canonical state. A direct
                # native-bridge smoke consumes that exact envelope just as
                # PracticeCommandCoordinator does, rather than assuming
                # the old flat response shape.
                var accepted_state: Variant = values.get("state")
                var accepted_outcome: Variant = values.get("outcome")
                if (not accepted_state is Dictionary or
                        not accepted_outcome is Dictionary or
                        int(accepted_outcome.get("version",-1)) != 1 or
                        str(accepted_outcome.get("action","")) != "score_ready" or
                        not bool(accepted_outcome.get("executed",false))):
                    _fail("Score-ready command did not publish its accepted action and state")
                    return true
                values = accepted_state
                # A fresh Practice Flow piece starts with Listen and may
                # still be preparing audio. Transport remains in 'admitting'
                # until the *Godot scene* commits physical score geometry.
                # This isolated bridge has no renderer and must never fake a
                # playback.present or claim a running take.
                if not bool(values.get("loaded",false)) or \
                        int(values.get("revision",-1)) != revision or \
                        str(values.get("mode","")) != "listen":
                    _fail("Score-ready acknowledgement changed the selected Listen source")
                    return true
                print("PIANO_NATIVE_REAL_SCORE_PREPARATION_OK revision=",revision)
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
