extends Node
## One asynchronous command slot backed by the embedded worker queue.
signal request_completed(result: int, response_code: int,
    headers: PackedStringArray, body: PackedByteArray)

var timeout := 5.0
var download_file := ""
var _bus: Node
var _pending_id := -1

func configure(bus: Node) -> void:
    _bus = bus

func request(command: String, payload: String = "", method: String = "GET") -> Error:
    if _bus == null or _pending_id >= 0:
        return ERR_BUSY
    if not command.begins_with("/") or method not in ["GET", "POST"]:
        return ERR_INVALID_PARAMETER
    _pending_id = int(_bus.submit(self, method, command, payload))
    return OK if _pending_id >= 0 else ERR_UNAVAILABLE

func cancel_request() -> void:
    # The worker may finish an obsolete command; ignore its completion.
    _pending_id = -1

func complete(identifier: int, code: int, body: PackedByteArray) -> void:
    if identifier != _pending_id:
        return
    _pending_id = -1
    if not download_file.is_empty() and code == 200:
        var file := FileAccess.open(download_file, FileAccess.WRITE)
        if file == null:
            code = 500
        else:
            file.store_buffer(body)
            file.close()
            body = PackedByteArray()
    request_completed.emit(OK, code, PackedStringArray(), body)
