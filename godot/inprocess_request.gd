extends Node
## One typed application operation in the embedded Python worker queue.
## No HTTP method, URL, headers, download adapter or network timeout.
signal request_completed(status: int, body: PackedByteArray)

var timeout := 5.0
var _bus: Node
var _pending_id := -1
var _deadline_ms := 0

func configure(bus: Node) -> void:
    _bus = bus
    set_process(false)

func request(operation: String, payload: Dictionary = {}) -> Error:
    if _bus == null or _pending_id >= 0:
        return ERR_BUSY
    if operation.is_empty():
        return ERR_INVALID_PARAMETER
    _pending_id = int(_bus.submit(self, operation, JSON.stringify(payload)))
    if _pending_id < 0:
        return ERR_UNAVAILABLE
    _deadline_ms = Time.get_ticks_msec() + maxi(1, int(timeout * 1000.0))
    set_process(true)
    return OK

func _process(_delta: float) -> void:
    if _pending_id < 0 or Time.get_ticks_msec() < _deadline_ms:
        return
    var expired_id: int = _pending_id
    _pending_id = -1
    set_process(false)
    if _bus != null:
        _bus.forget(expired_id, self)
    request_completed.emit(3, JSON.stringify(
        {"error": "Embedded operation exceeded its deadline"}).to_utf8_buffer())

func cancel_request() -> void:
    # A timed-out or canceled request must not leak a registered weakref.
    var canceled_id: int = _pending_id
    _pending_id = -1
    set_process(false)
    if canceled_id >= 0 and _bus != null:
        _bus.forget(canceled_id, self)

func complete(identifier: int, status: int, body: PackedByteArray) -> void:
    if identifier != _pending_id:
        return
    _pending_id = -1
    set_process(false)
    request_completed.emit(status, body)
