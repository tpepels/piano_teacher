extends SceneTree
const Owner := preload("res://midi_device_coordinator.gd")

class FakeSettings:
    extends RefCounted
    var names: Array = []
    var showed := false
    var message := ""
    var selection := ""
    func present_devices(choices: Array, _connected: String, show: bool) -> void:
        names = choices
        showed = show
    func present_message(text: String) -> void:
        message = text
    func present_device_selection(value: String) -> void:
        selection = value

var posts: Array = []
func _decode(body: PackedByteArray) -> Variant:
    return JSON.parse_string(body.get_string_from_utf8())
func _failure(code: int, _body: PackedByteArray) -> String:
    return "Command " + str(code)
func _post(path: String, payload: Dictionary) -> void:
    posts.append({"path":path, "payload":payload})

func _initialize() -> void:
    var failures := 0
    var settings := FakeSettings.new()
    var owner := Owner.new()
    owner.configure(settings,
        _decode, _failure, _post)
    owner.show_picker()
    if not owner.picker_requested or owner.pending:
        failures += 1
    owner.receive(200, '{"devices":["Piano A","MIDI Through"]}'.to_utf8_buffer(),
        "settings", "", "Piano A")
    if owner.picker_requested or not settings.showed or posts.size() != 1:
        failures += 1
    if posts.size() == 1 and posts[0]["payload"] != {"name":"Piano A"}:
        failures += 1
    owner.receive(200, '{"devices":["Piano A"]}'.to_utf8_buffer(),
        "settings", "Already connected", "Piano A")
    if posts.size() != 1:
        failures += 1
    owner.receive(200, '{"devices":["MIDI Through"]}'.to_utf8_buffer(),
        "settings", "", "MIDI Through")
    if posts.size() != 1:
        failures += 1
    owner.show_picker()
    owner.receive(503, PackedByteArray(), "settings", "", "Piano A")
    if owner.picker_requested or not settings.message.contains("Command 503"):
        failures += 1
    owner.choose("Piano B")
    if settings.selection != "Piano B" or posts.size() != 2:
        failures += 1
    print("MIDI_DEVICE_COORDINATOR_FAILURES:", failures)
    quit(0 if failures == 0 else 1)
