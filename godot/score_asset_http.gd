extends RefCounted

# Thin HTTP transport for the independent ScoreAssetSession. Each callback
# returns the exact request ID granted by its owner; aborting an in-flight
# old HTTP request cannot accidentally publish that revision's score.
var layout_request
var model_request
var _owner
var _base_url := ""
var _inprocess_bus: Node
var _request_ids := {"layout":-1, "model":-1}

func attach(host: Node, owner, base_url: String, bus: Node = null) -> void:
    _owner = owner
    _base_url = base_url
    _inprocess_bus = bus
    if bus != null:
        layout_request = preload("res://inprocess_request.gd").new()
        model_request = preload("res://inprocess_request.gd").new()
        layout_request.configure(bus)
        model_request.configure(bus)
    else:
        layout_request = HTTPRequest.new()
        model_request = HTTPRequest.new()
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
    # Score revisions can advance while HTTP is still in flight.
    # Cancel before replacing the slot: a stale response must never inherit
    # a newer request's ID.
    if int(_request_ids.get(kind, -1)) != -1:
        request.cancel_request()
    _request_ids[kind] = request_id
    request.timeout = timeout_seconds
    var error: Error = request.request(_base_url + path)
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
