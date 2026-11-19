extends RefCounted
## UI intent and request lifecycle only. No musical scheduling or score
## admission lives here; every timed route uses Python PlaybackCoordinator
## and the one ScoreAdmissionGateway.
const CommandRequestState := preload("res://command_request_state.gd")
const CommandSuccessPolicy := preload("res://command_success_policy.gd")

signal succeeded(decision: Dictionary, opened: Variant, code: int, body: PackedByteArray, started_ms: int)
signal learning_accepted(operation: String, values: Dictionary)
signal library_requested(piece: String, resume_saved: bool)
signal refresh_requested
signal fingering_changed(message: String)
signal score_error_cleared

var state = CommandRequestState.new()
var request_token := 0
var last_published_control_started_ms := -1
var last_state: Dictionary = {}
var practice_view
var settings_view
var metronome_frame
var action_request
var command_failure_presenter
var fingering_save_error := ""

func configure(practice, settings, metronome, _flow, _clock, request,
        failure_presenter) -> void:
    practice_view = practice
    settings_view = settings
    metronome_frame = metronome
    action_request = request
    command_failure_presenter = failure_presenter

func _decode_json(body: PackedByteArray) -> Variant:
    return JSON.parse_string(body.get_string_from_utf8()) if not body.is_empty() else null

func _command_failure(code: int, body: PackedByteArray) -> String:
    var response: Variant = _decode_json(body)
    return str(response.get("error","Command failed (status %d)" % code)) \
        if response is Dictionary else \
        "Embedded practice engine unavailable (status %d)" % code

func _flush_transport_action() -> void:
    var action: String = state.take_transport()
    if not action.is_empty():
        request_action({"action":action},last_state)

func tick(_now_ms: int) -> void:
    pass

func request_action(command: Dictionary, presentation_facts: Dictionary) -> void:
    last_state = presentation_facts
    var action: String = str(command.get("action",""))
    var previous: String = state.control_action
    if not state.action_requested(action):
        practice_view.begin_action(action,previous)
        return
    practice_view.begin_action(action)
    if action not in ["start","restart","resume","score_ready"]:
        metronome_frame.cancel_reserved_count_in()
    request_command("practice.command",command)

func request_command(operation: String, payload: Dictionary) -> void:
    if not state.begin(operation,Time.get_ticks_msec()):
        return
    request_token += 1
    practice_view.present_busy(true)
    settings_view.present_busy(true)
    var err: int = state.dispatch(action_request,operation,payload)
    if err == OK:
        return
    practice_view.present_busy(false)
    settings_view.present_busy(false)
    if operation == "practice.command":
        practice_view.finish_action()
    var message := "Cannot reach practice engine (status %d)" % err
    if operation == "fingering.correct":
        fingering_save_error = message
        fingering_changed.emit(fingering_save_error)
    var queued_library_failed: bool = state.discard_library()
    command_failure_presenter.present(
        message,operation,queued_library_failed)
    _flush_transport_action()

func accept_response(token: int, code: int, body: PackedByteArray) -> void:
    if token != request_token or not state.pending:
        return
    var completed: Dictionary = state.finish()
    practice_view.present_busy(false)
    settings_view.present_busy(false)
    var operation: String = str(completed["operation"])
    if operation == "practice.command":
        practice_view.finish_action()
    if code != 0:
        if operation == "practice.command":
            metronome_frame.cancel_reserved_count_in()
        var message := _command_failure(code,body)
        if operation == "fingering.correct":
            fingering_save_error = message
            fingering_changed.emit(fingering_save_error)
        var queued_library_failed: bool = state.discard_library()
        command_failure_presenter.present(
            message,operation,queued_library_failed)
        _flush_transport_action()
        return
    var opened: Variant = _decode_json(body) if operation == "library.open" else null
    if operation in ["learning.export","learning.delete_piece","learning.delete_learner"]:
        var result: Variant = _decode_json(body)
        learning_accepted.emit(operation,
            result if result is Dictionary else {})
    var decision: Dictionary = CommandSuccessPolicy.decide(
        operation,str(completed["action"]),bool(completed["resume_saved"]),opened)
    if str(decision["kind"]) == "fingering":
        fingering_save_error = ""
    elif str(decision["kind"]) == "library_open":
        score_error_cleared.emit()
    if bool(decision.get("publish_state",false)):
        last_published_control_started_ms = maxi(
            last_published_control_started_ms,int(completed["started_ms"]))
    succeeded.emit(decision,opened,code,body,int(completed["started_ms"]))
    _flush_transport_action()
    refresh_requested.emit()
    var deferred: Dictionary = state.take_library()
    if not str(deferred["piece"]).is_empty():
        library_requested.emit(
            str(deferred["piece"]),bool(deferred["resume_saved"]))
