extends SceneTree
const Request := preload("res://inprocess_request.gd")

class FakeBus:
    extends Node
    var next_id := 100
    var pending := {}
    var enabled := true

    func submit(requester: Node, _operation: String, _payload: String) -> int:
        if not enabled:
            return -1
        var identifier := next_id
        next_id += 1
        pending[identifier] = weakref(requester)
        return identifier

    func forget(identifier: int, requester: Node) -> void:
        var handle: WeakRef = pending.get(identifier)
        if handle != null and handle.get_ref() == requester:
            pending.erase(identifier)

    func deliver(identifier: int, status: int, body: PackedByteArray) -> void:
        var handle: WeakRef = pending.get(identifier)
        pending.erase(identifier)
        var receiver: Variant = handle.get_ref() if handle != null else null
        if receiver != null:
            receiver.complete(identifier,status,body)


func _initialize() -> void:
    var failures := 0
    var bus := FakeBus.new()
    root.add_child(bus)
    var request := Request.new()
    root.add_child(request)
    request.configure(bus)
    var completed := []
    request.request_completed.connect(func(status: int, _body: PackedByteArray):
        completed.append(status))

    if request.request("practice.command", {"action":"start"}) != OK:
        failures += 1
    if request.request("practice.command") != ERR_BUSY:
        failures += 1
    request._deadline_ms = 0
    request._process(0.0)
    if completed != [3] or not bus.pending.is_empty():
        failures += 1
    bus.deliver(100,0,PackedByteArray())
    if completed != [3]:
        failures += 1

    if request.request("library.open", {"id":"music.mid"}) != OK:
        failures += 1
    bus.deliver(100,0,PackedByteArray()) # Timed-out prior request.
    if completed != [3]:
        failures += 1
    bus.deliver(101,0,PackedByteArray())
    if completed != [3,0] or not bus.pending.is_empty():
        failures += 1
    bus.deliver(101,0,PackedByteArray()) # Duplicate completion.
    if completed != [3,0]:
        failures += 1

    if request.request("practice.command") != OK:
        failures += 1
    request.cancel_request()
    if not bus.pending.is_empty():
        failures += 1
    bus.deliver(102,0,PackedByteArray())
    if completed != [3,0]:
        failures += 1

    bus.enabled = false
    if request.request("practice.command") != ERR_UNAVAILABLE:
        failures += 1
    if not bus.pending.is_empty():
        failures += 1
    print("INPROCESS_REQUEST_LIFECYCLE_FAILURES:", failures)
    quit(0 if failures == 0 else 1)
