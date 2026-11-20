extends RefCounted
signal open_requested(identifier: String, resume_saved: bool)
const Reply := preload("res://inprocess_request.gd")

# Own catalogue, startup selection and library health lifecycle. Commands
# remain with PracticeCommandCoordinator; no library event starts a take.
var catalog_request
var health_request
var pending := false
var health_pending := false
var health_running := false
var _library_view
var _home_view
var _send_command: Callable
var startup_checked := false

func configure(library_view, home_view, send_command: Callable) -> void:
    _library_view = library_view
    _home_view = home_view
    _send_command = send_command

func attach_requests(catalog, health) -> void:
    catalog_request = catalog
    health_request = health

func request_catalog() -> void:
    if pending or catalog_request == null:
        return
    pending = true
    if catalog_request.request("library.catalog") != OK:
        pending = false

func on_catalog(code: int, body: PackedByteArray) -> void:
    pending = false
    if code != 0:
        _library_view.present_request_error(Reply.failure_message(code, body))
        _home_view.present_catalog_unavailable()
        return
    var parsed: Variant = Reply.decode_reply(body)
    if not parsed is Dictionary:
        return
    _library_view.present_catalog(parsed)
    _home_view.present_catalog(parsed)
    _resume_startup_piece(parsed)
    request_health()

func _resume_startup_piece(catalog: Dictionary) -> void:
    if startup_checked:
        return
    startup_checked = true
    var identifier := str(catalog.get("last_piece", ""))
    if identifier.is_empty():
        return
    for entry in catalog.get("pieces", []):
        if entry is Dictionary and str(entry.get("id", "")) == identifier:
            open_requested.emit(identifier,true)
            return

func request_health() -> void:
    if health_request == null or health_pending:
        return
    health_pending = true
    if health_request.request("library.health_status") != OK:
        health_pending = false

func start_health(action_pending: bool) -> void:
    if action_pending or health_running:
        return
    _library_view.present_health_message("Starting music file check…")
    _send_command.call("library.health.start", {})

func on_health(code: int, body: PackedByteArray) -> void:
    health_pending = false
    if code != 0:
        _library_view.present_health_message(
            "Cannot check music files: " + Reply.failure_message(code, body))
        return
    var parsed: Variant = Reply.decode_reply(body)
    if not parsed is Dictionary:
        return
    health_running = bool(parsed.get("running", false))
    _library_view.present_health(parsed)
