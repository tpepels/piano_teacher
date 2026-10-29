extends RefCounted

# Own the library catalogue and health-poll lifecycle; application navigation
# and the /library/open transport command remain with the main controller.
var catalog_request: HTTPRequest
var health_request: HTTPRequest
var pending := false
var health_pending := false
var health_running := false
var _url: String
var _library_view
var _home_view
var _decode: Callable
var _failure: Callable
var _send_post: Callable

func configure(url: String, library_view, home_view,
        decode: Callable, failure: Callable, send_post: Callable) -> void:
    _url = url
    _library_view = library_view
    _home_view = home_view
    _decode = decode
    _failure = failure
    _send_post = send_post

func attach_requests(catalog: HTTPRequest, health: HTTPRequest) -> void:
    catalog_request = catalog
    health_request = health

func request_catalog() -> void:
    if pending or catalog_request == null:
        return
    pending = true
    if catalog_request.request(_url + "/library") != OK:
        pending = false

func on_catalog(_result: int, code: int,
        _headers: PackedStringArray, body: PackedByteArray) -> void:
    pending = false
    if code != 200:
        _library_view.present_request_error(_failure.call(code, body))
        _home_view.present_catalog_unavailable()
        return
    var parsed: Variant = _decode.call(body)
    if not parsed is Dictionary:
        return
    _library_view.present_catalog(parsed)
    _home_view.present_catalog(parsed)
    request_health()

func request_health() -> void:
    if health_request == null or health_pending:
        return
    health_pending = true
    if health_request.request(_url + "/library/health") != OK:
        health_pending = false

func start_health(action_pending: bool) -> void:
    if action_pending or health_running:
        return
    _library_view.present_health_message("Starting music file check…")
    _send_post.call("/library/health", {})

func on_health(_result: int, code: int,
        _headers: PackedStringArray, body: PackedByteArray) -> void:
    health_pending = false
    if code != 200:
        _library_view.present_health_message(
            "Cannot check music files: " + _failure.call(code, body))
        return
    var parsed: Variant = _decode.call(body)
    if not parsed is Dictionary:
        return
    health_running = bool(parsed.get("running", false))
    _library_view.present_health(parsed)
