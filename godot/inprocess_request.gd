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
    _pending_id = -1
    set_process(false)
    request_completed.emit(3, JSON.stringify(
        {"error": "Embedded operation exceeded its deadline"}).to_utf8_buffer())

func cancel_request() -> void:
    # An obsolete worker result can complete but cannot change current state.
    _pending_id = -1
    set_process(false)

func complete(identifier: int, status: int, body: PackedByteArray) -> void:
    if identifier != _pending_id:
        return
    _pending_id = -1
    set_process(false)
    request_completed.emit(status, body)
