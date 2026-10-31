extends RefCounted
## Score layout and model commands. Revision checks prevent stale publication.
var layout_request
var model_request
var _owner
var _request_ids := {"layout": -1, "model": -1}

func attach(host: Node, owner, bus: Node) -> void:
    _owner = owner
    layout_request = preload("res://inprocess_request.gd").new()
    model_request = preload("res://inprocess_request.gd").new()
    layout_request.configure(bus)
    model_request.configure(bus)
    layout_request.timeout = 90.0
    model_request.timeout = 5.0
    host.add_child(layout_request)
    host.add_child(model_request)
    layout_request.request_completed.connect(
        func(_result: int, code: int, _headers: PackedStringArray,
                body: PackedByteArray):
            deliver("layout", code, body))
    model_request.request_completed.connect(
        func(_result: int, code: int, _headers: PackedStringArray,
                body: PackedByteArray):
            deliver("model", code, body))
    owner.request_requested.connect(start)

func start(kind: String, request_id: int, path: String,
        timeout_seconds: float) -> void:
    var request = layout_request if kind == "layout" else model_request
    if request == null:
        _owner.request_start_result(kind, request_id, ERR_UNAVAILABLE,
            Time.get_ticks_msec())
        return
    # A cancelled or outdated response cannot publish a different revision.
    if int(_request_ids.get(kind, -1)) != -1:
        request.cancel_request()
    _request_ids[kind] = request_id
    request.timeout = timeout_seconds
    var error: Error = request.request(path)
    if error != OK:
        _request_ids[kind] = -1
        _owner.request_start_result(kind, request_id, error,
            Time.get_ticks_msec())

func deliver(kind: String, code: int, body: PackedByteArray) -> void:
    var request_id: int = int(_request_ids.get(kind, -1))
    if request_id < 0:
        return
    _request_ids[kind] = -1
    _owner.complete_response(kind, request_id, code, body,
        Time.get_ticks_msec())
