extends RefCounted

## Owns MIDI discovery, selected-device restoration and picker state.
const Reply := preload("res://inprocess_request.gd")
var request
var pending := false
var picker_requested := false
var names: Array = []
var _settings
var _send_command: Callable
var _navigation
var _inbox
var _preferences: WeakRef

func configure(settings, send_command: Callable) -> void:
    _settings = settings
    _send_command = send_command

func bind_context(navigation, inbox, settings_session) -> void:
    _navigation = navigation
    _inbox = inbox
    _preferences = weakref(settings_session)

func on_devices(code: int, body: PackedByteArray) -> void:
    var settings = _preferences.get_ref()
    receive(code,body,_navigation.current_screen,
        str(_inbox.current.get("device","")),
        str(settings.preferences.get("midi_device","")) if settings != null else "")

func attach_request(value) -> void:
    request = value

func discover() -> void:
    if pending or request == null:
        return
    pending = true
    if request.request("midi.devices") != OK:
        pending = false

func show_picker() -> void:
    picker_requested = true
    discover()

func choose(name: String) -> void:
    _send_command.call("midi.device.select", {"name":name})
    if not name.is_empty():
        _settings.present_device_selection(name)

func maybe_restore(saved: String, connected: String) -> void:
    if connected.is_empty() and names.has(saved) and not saved.is_empty() \
            and not saved.to_lower().contains("midi through"):
        choose(saved)

func receive(code: int, body: PackedByteArray, screen: String,
        connected: String, saved: String) -> void:
    pending = false
    if code != 0:
        picker_requested = false
        if screen == "settings":
            _settings.present_message(
                "MIDI device scan failed: " + Reply.failure_message(code, body))
        return
    var parsed: Variant = Reply.decode_reply(body)
    if not parsed is Dictionary:
        picker_requested = false
        return
    names = parsed.get("devices", [])
    var show: bool = picker_requested
    picker_requested = false
    _settings.present_devices(names, connected, show)
    maybe_restore(saved, connected)
