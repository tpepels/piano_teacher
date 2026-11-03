extends SceneTree
const State := preload("res://command_request_state.gd")

class Adapter:
    extends RefCounted
    var timeout := 0.0
    var result_code := 0
    var calls: Array = []
    func request(operation: String, payload: Dictionary) -> int:
        calls.append([operation,payload])
        return result_code

func _initialize() -> void:
    var failures := 0
    var state := State.new()
    if not state.action_requested("start") or state.control_action != "start":
        failures += 1
    if not state.begin("practice.command",150):
        failures += 1
    if state.begin("settings.update",160):
        failures += 1
    if state.action_requested("pause") or state.take_transport() != "pause":
        failures += 1
    # Requests can be queued while another command is awaiting its reply.
    state.queue_library("score.mid",true)
    if state.action_requested("play") or state.control_action != "start":
        failures += 1
    var first: Dictionary = state.finish()
    if state.pending or first["operation"] != "practice.command" or first["action"] != "start" or \
            int(first["started_ms"]) != 150 or first["resume_saved"]:
        failures += 1
    var queued: Dictionary = state.take_library()
    if queued["piece"] != "score.mid" or not queued["resume_saved"]:
        failures += 1
    if not state.take_library()["piece"].is_empty():
        failures += 1
    if not state.take_transport().is_empty():
        failures += 1
    state.resume_requested = true
    if not state.begin("library.open",200):
        failures += 1
    var opened: Dictionary = state.finish()
    if not opened["resume_saved"] or state.resume_requested:
        failures += 1
    state.queue_library("other.mid",false)
    if not state.discard_library() or state.discard_library():
        failures += 1
    if not state.begin("fingering.correct",250):
        failures += 1
    var adapter := Adapter.new()
    if state.dispatch(adapter,"fingering.correct",{"finger":2}) != OK or \
            adapter.timeout != 360.0 or adapter.calls.size() != 1 or \
            adapter.calls[0][0] != "fingering.correct" or \
            adapter.calls[0][1].get("finger") != 2:
        failures += 1
    state.finish()
    if not state.begin("practice.command",300):
        failures += 1
    adapter.result_code = FAILED
    if state.dispatch(adapter,"practice.command",{"action":"pause"}) != FAILED or \
            state.pending or adapter.timeout != 5.0:
        failures += 1
    if not state.begin("practice.command",310):
        failures += 1
    # A canceled callback is never allowed to finish an inactive command.
    var current: Dictionary = state.finish()
    if current["operation"] != "practice.command" or not state.finish().is_empty():
        failures += 1
    if state.pending or not state.operation.is_empty() or not state.control_action.is_empty():
        failures += 1
    # Non-command operations cannot inherit a previous practice action.
    state.action_requested("resume")
    if not state.begin("settings.update",320):
        failures += 1
    var saved: Dictionary = state.finish()
    if saved["action"] != "" or saved["operation"] != "settings.update":
        failures += 1
    # Immediate transport failure clears the request owner.
    state.action_requested("start")
    state.begin("practice.command",350)
    state.request_failed()
    if state.pending or not state.operation.is_empty() or not state.finish().is_empty():
        failures += 1
    print("COMMAND_REQUEST_STATE_FAILURES:",failures)
    quit(0 if failures == 0 else 1)
