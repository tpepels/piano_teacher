extends Node
## Main-thread completion fanout for the in-process Godot GDExtension.
## Python commands run on its worker; it never invokes Godot from that thread.
var native
var pending: Dictionary = {}
var ready_error := ""

func _ready() -> void:
    if not ClassDB.class_exists("PianoNative"):
        ready_error = "PianoNative extension is missing. Build and bundle it first."
        push_error(ready_error)
        set_process(false)
        return
    native = ClassDB.instantiate("PianoNative")
    if native == null:
        ready_error = "Could not instantiate the embedded Python extension"
        set_process(false)

func is_ready() -> bool:
    return native != null and bool(native.call("is_ready"))

func submit(requester: Node, method: String, path: String, body: String) -> int:
    if native == null or not is_ready():
        return -1
    var identifier := int(native.call("submit", method, path, body))
    if identifier >= 0:
        pending[identifier] = weakref(requester)
    return identifier

func poll_midi(after_sequence: int) -> Array:
    if not is_ready():
        return []
    var parsed: Variant = JSON.parse_string(str(
        native.call("live_events_json", after_sequence)))
    return parsed if parsed is Array else []

func _process(_delta: float) -> void:
    if native == null:
        return
    if not is_ready():
        var error := str(native.call("failure_message"))
        if not error.is_empty() and error != ready_error:
            ready_error = error
            push_error("Embedded Python: " + error)
        return
    for reply in native.call("take_responses"):
        if not reply is Dictionary:
            continue
        var identifier := int(reply.get("id", -1))
        var handle: WeakRef = pending.get(identifier)
        pending.erase(identifier)
        var requester: Variant = handle.get_ref() if handle != null else null
        if requester != null and is_instance_valid(requester):
            requester.complete(identifier,
                int(reply.get("status", 500)),
                reply.get("body", PackedByteArray()))
