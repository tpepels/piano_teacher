extends Node
## One typed application operation in the embedded Python worker queue.
## No HTTP method, URL, headers, download adapter or network timeout.
signal request_completed(status: int, body: PackedByteArray)

var timeout := 5.0
var _bus: Node
var _pending_id := -1
var _deadline_ms := 0
var _operation := ""
# Test stimulus at the actual embedded-worker reply seam. No production
# lesson, queue, clock or grading policy is replaced by this injector.

static func decode_reply(body: PackedByteArray) -> Variant:
    return JSON.parse_string(body.get_string_from_utf8()) if not body.is_empty() else null

static func failure_message(code: int, body: PackedByteArray) -> String:
    var response: Variant = decode_reply(body)
    return str(response.get("error", "Command failed (status %d)" % code)) \
        if response is Dictionary else \
        "Embedded practice engine unavailable (status %d)" % code

func configure(bus: Node) -> void:
    _bus = bus
    set_process(false)

func is_pending() -> bool:
    return _pending_id >= 0

func request(operation: String, payload: Dictionary = {}) -> Error:
    if _bus == null or _pending_id >= 0:
        return ERR_BUSY
    if operation.is_empty():
        return ERR_INVALID_PARAMETER
    _operation = operation
    _pending_id = int(_bus.submit(self, operation, JSON.stringify(payload)))
    if _pending_id < 0:
        _operation = ""
        return ERR_UNAVAILABLE
    _deadline_ms = Time.get_ticks_msec() + maxi(1, int(timeout * 1000.0))
    set_process(true)
    return OK

func _process(_delta: float) -> void:
    if _pending_id < 0 or Time.get_ticks_msec() < _deadline_ms:
        return
    var expired_id: int = _pending_id
    _pending_id = -1
    _operation = ""
    set_process(false)
    if _bus != null:
        _bus.forget(expired_id, self)
    request_completed.emit(3, JSON.stringify(
        {"error": "Embedded operation exceeded its deadline"}).to_utf8_buffer())

func cancel_request() -> void:
    # A timed-out or canceled request must not leak a registered weakref.
    var canceled_id: int = _pending_id
    _pending_id = -1
    _operation = ""
    set_process(false)
    if canceled_id >= 0 and is_instance_valid(_bus):
        _bus.forget(canceled_id, self)

func complete(identifier: int, status: int, body: PackedByteArray) -> void:
    if identifier != _pending_id:
        return
    _pending_id = -1
    _operation = ""
    set_process(false)
    request_completed.emit(status, body)
