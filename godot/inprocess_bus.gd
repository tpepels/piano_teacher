extends Node
## Main-thread completion fanout for the in-process Godot GDExtension.
## Python commands run on its worker; it never invokes Godot from that thread.
var native
var pending: Dictionary = {}
var ready_error := ""
var feedback_request_id := -1
var feedback_reply: Variant = null

const EXTENSION_PATH := "res://native/piano_bridge.gdextension"

func _failure(message: String) -> void:
    ready_error = message
    push_error(message)
    set_process(false)

func _ready() -> void:
    if not ClassDB.class_exists("PianoNative"):
        # A newly generated .gdextension is not necessarily in Godot's
        # resource index until the project is imported in editor mode.
        # Try a direct load as well; report the real status instead of
        # suggesting that the binary was never compiled.
        if not FileAccess.file_exists(EXTENSION_PATH):
            _failure("Native extension manifest missing: " + EXTENSION_PATH +
                " (rebuild with scripts/build-inprocess.sh)")
            return
        var load_status: int = GDExtensionManager.load_extension(EXTENSION_PATH)
        if not ClassDB.class_exists("PianoNative"):
            _failure("Unable to register PianoNative (GDExtension load status %d). " % load_status +
                "Check the .so dependency errors above. Run " +
                "godot --headless --editor --import --path godot to refresh the project.")
            return
    native = ClassDB.instantiate("PianoNative")
    if native == null:
        _failure("GDExtension is registered but PianoNative cannot be instantiated")
        return

func is_ready() -> bool:
    return native != null and bool(native.call("is_ready"))

func submit(requester: Node, operation: String, payload: String) -> int:
    if native == null or not is_ready():
        return -1
    var identifier := int(native.call("submit", operation, payload))
    if identifier >= 0:
        pending[identifier] = weakref(requester)
    return identifier

func forget(identifier: int, requester: Node) -> void:
    # The worker may still finish; only its obsolete Godot callback is
    # detached. Never drop a different request if IDs are reused.
    var handle: WeakRef = pending.get(identifier)
    if handle != null and handle.get_ref() == requester:
        pending.erase(identifier)


## The completed feedback-log reply, if one arrived since the last call.
func take_feedback_events() -> Variant:
    var reply: Variant = feedback_reply
    feedback_reply = null
    return reply

## Acknowledge processed events and ask for every later one. Never call
## CPython or acquire its GIL on the Godot rendering thread: the one
## outstanding read goes through the existing worker. A failed read loses
## nothing, because the backend keeps unacknowledged events.
func request_feedback_events(acknowledged: int) -> void:
    if feedback_request_id < 0 and is_ready():
        feedback_request_id = int(native.call("submit", "feedback.events",
            JSON.stringify({"acknowledged": maxi(0, acknowledged)})))

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
        if identifier == feedback_request_id:
            feedback_request_id = -1
            if int(reply.get("status", 3)) == 0:
                var bytes: PackedByteArray = reply.get("body", PackedByteArray())
                var parsed: Variant = JSON.parse_string(bytes.get_string_from_utf8())
                feedback_reply = parsed if parsed is Dictionary else null
            else:
                push_error("NOTE_FEEDBACK_READ_FAILED: status %d" % int(reply.get("status", 3)))
            continue
        var handle: WeakRef = pending.get(identifier)
        pending.erase(identifier)
        var requester: Variant = handle.get_ref() if handle != null else null
        if requester != null and is_instance_valid(requester):
            requester.complete(identifier,
                int(reply.get("status", 3)),
                reply.get("body", PackedByteArray()))
