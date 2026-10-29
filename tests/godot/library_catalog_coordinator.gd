extends SceneTree
const Coordinator := preload("res://library_catalog_coordinator.gd")

class FakeLibrary:
    extends RefCounted
    var catalog: Dictionary = {}
    var error := ""
    var health: Dictionary = {}
    var message := ""
    func present_catalog(data: Dictionary) -> void:
        catalog = data
    func present_request_error(reason: String) -> void:
        error = reason
    func present_health(data: Dictionary) -> void:
        health = data
    func present_health_message(reason: String) -> void:
        message = reason

class FakeHome:
    extends RefCounted
    var catalog: Dictionary = {}
    var unavailable := false
    func present_catalog(data: Dictionary) -> void:
        catalog = data
    func present_catalog_unavailable() -> void:
        unavailable = true

var posts: Array = []
func _decode(body: PackedByteArray) -> Variant:
    return JSON.parse_string(body.get_string_from_utf8())
func _failure(code: int, _body: PackedByteArray) -> String:
    return "HTTP " + str(code)
func _post(path: String, payload: Dictionary) -> void:
    posts.append({"path":path,"payload":payload})

func _initialize() -> void:
    var failures := 0
    var lib := FakeLibrary.new()
    var home := FakeHome.new()
    var coordinator := Coordinator.new()
    coordinator.configure("http://127.0.0.1:8765",lib,home,
        _decode, _failure, _post)
    coordinator.request_catalog()
    if coordinator.pending:
        failures += 1
    coordinator.on_catalog(0,200,PackedStringArray(),
        '{"pieces":[{"id":"test"}]}'.to_utf8_buffer())
    if lib.catalog.get("pieces",[]).size() != 1 or home.catalog != lib.catalog:
        failures += 1
    coordinator.on_catalog(0,503,PackedStringArray(),PackedByteArray())
    if lib.error != "HTTP 503" or not home.unavailable:
        failures += 1
    coordinator.start_health(true)
    if posts.size() != 0:
        failures += 1
    coordinator.start_health(false)
    if posts.size() != 1 or posts[0]["path"] != "/library/health":
        failures += 1
    coordinator.on_health(0,200,PackedStringArray(),
        '{"running":true,"files":7}'.to_utf8_buffer())
    if not coordinator.health_running or lib.health.get("files",-1) != 7:
        failures += 1
    coordinator.start_health(false)
    if posts.size() != 1:
        failures += 1
    coordinator.on_health(0,500,PackedStringArray(),PackedByteArray())
    if lib.message != "Cannot check music files: HTTP 500":
        failures += 1
    print("LIBRARY_COORDINATOR_FAILURES:",failures)
    quit(0 if failures == 0 else 1)
