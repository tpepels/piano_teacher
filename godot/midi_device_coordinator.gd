extends RefCounted

# Owns MIDI-input discovery requests and picker state. The main controller
# retains backend /device transport actions and navigation, passed as callbacks.
var request: HTTPRequest
var pending := false
var picker_requested := false
var names: Array = []
var _url: String
var _settings
var _decode: Callable
var _failure: Callable
var _send_post: Callable

func configure(url: String, settings, decode: Callable,
        failure: Callable, send_post: Callable) -> void:
    _url = url
    _settings = settings
    _decode = decode
    _failure = failure
    _send_post = send_post

func attach_request(value: HTTPRequest) -> void:
    request = value

func discover() -> void:
    if pending or request == null:
        return
    pending = true
    if request.request(_url + "/devices") != OK:
        pending = false

func show_picker() -> void:
    picker_requested = true
    discover()

func choose(name: String) -> void:
    _send_post.call("/device", {"name":name})
    if not name.is_empty():
        _settings.present_device_selection(name)

func maybe_restore(saved: String, connected: String) -> void:
    if connected.is_empty() and names.has(saved) and not saved.is_empty() \
            and not saved.to_lower().contains("midi through"):
        choose(saved)

func receive(code: int, body: PackedByteArray, screen: String,
        connected: String, saved: String) -> void:
    pending = false
    if code != 200:
        picker_requested = false
        if screen == "settings":
            _settings.present_message(
                "MIDI device scan failed: " + _failure.call(code, body))
        return
    var parsed: Variant = _decode.call(body)
    if not parsed is Dictionary:
        picker_requested = false
        return
    names = parsed.get("devices", [])
    var show: bool = picker_requested
    picker_requested = false
    _settings.present_devices(names, connected, show)
    maybe_restore(saved, connected)
