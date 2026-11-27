extends RefCounted
## One in-process ScoreBundle request for the exact source and revision.
## Current and future scores use the same layout plus original-note contract.
var bundle_request
var _owner
var _request_id := -1

func attach(host: Node, owner, bus: Node) -> void:
    _owner = owner
    bundle_request = preload("res://inprocess_request.gd").new()
    bundle_request.configure(bus)
    bundle_request.timeout = 90.0
    host.add_child(bundle_request)
    bundle_request.request_completed.connect(
        func(code: int, body: PackedByteArray):
            deliver(code, body))
    owner.request_requested.connect(start)
    owner.request_cancelled.connect(cancel)

func start(kind: String, request_id: int, path: String,
        timeout_seconds: float, identity: Dictionary) -> void:
    if kind != "bundle" or path != "score.bundle" or bundle_request == null:
        _owner.request_start_result(kind, request_id, ERR_UNAVAILABLE,
            Time.get_ticks_msec())
        return
    # An obsolete reply cannot install a model for a newer stage revision.
    cancel()
    _request_id = request_id
    bundle_request.timeout = timeout_seconds
    var error: Error = bundle_request.request(path,identity)
    if error != OK:
        _request_id = -1
        _owner.request_start_result(kind, request_id, error,
            Time.get_ticks_msec())

func cancel() -> void:
    _request_id = -1
    if is_instance_valid(bundle_request):
        bundle_request.cancel_request()


func deliver(code: int, body: PackedByteArray) -> void:
    var request_id: int = _request_id
    if request_id < 0:
        return
    _request_id = -1
    _owner.complete_response("bundle", request_id, code, body,
        Time.get_ticks_msec())
