extends Node
## Drop-in asynchronous request slot for the embedded Python worker.
## Keeps the signal/data contract expected by ScoreAssetSession and Main,
## but never constructs HTTPRequest, sockets or a URL connection.
signal request_completed(result: int, response_code: int,
    headers: PackedStringArray, body: PackedByteArray)

var timeout := 5.0
var download_file := ""
var _bus
var _pending_id := -1

func configure(bus: Node) -> void:
    _bus = bus

func request(path: String, _headers: PackedStringArray = PackedStringArray(),
        method: int = HTTPClient.METHOD_GET, body: String = "") -> Error:
    if _bus == null or _pending_id >= 0:
        return ERR_BUSY
    var normalized := path
    if path.begins_with("http://127.0.0.1:8765"):
        normalized = path.trim_prefix("http://127.0.0.1:8765")
    if not normalized.begins_with("/"):
        return ERR_INVALID_PARAMETER
    var verb := "POST" if method == HTTPClient.METHOD_POST else "GET"
    _pending_id = int(_bus.submit(self, verb, normalized, body))
    return OK if _pending_id >= 0 else ERR_UNAVAILABLE

func cancel_request() -> void:
    # A finished old job is ignored; it cannot take another revision's slot.
    # The Python engine may still be completing that job in the worker queue.
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
    request_completed.emit(0, code, PackedStringArray(), body)
