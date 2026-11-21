extends RefCounted
## UI intent and request lifecycle only. No musical scheduling or score
## admission lives here; every timed route uses Python PlaybackCoordinator
## and the one ScoreAdmissionGateway.
const CommandRequestState := preload("res://command_request_state.gd")
const CommandSuccessPolicy := preload("res://command_success_policy.gd")
const ControlPolicy := preload("res://practice_control_policy.gd")
const Reply := preload("res://inprocess_request.gd")

signal succeeded(decision: Dictionary, opened: Variant, code: int, body: PackedByteArray, started_ms: int)
signal learning_accepted(operation: String, values: Dictionary)
signal library_requested(piece: String, resume_saved: bool)
signal refresh_requested
signal library_open_status(message: String)

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
var score_session

func configure(practice, settings, metronome, request,
        failure_presenter, assets) -> void:
    practice_view = practice
    settings_view = settings
    metronome_frame = metronome
    action_request = request
    command_failure_presenter = failure_presenter
    score_session = assets

func receive(code: int, body: PackedByteArray) -> void:
    accept_response(request_token,code,body)

func primary() -> void:
    _apply_control(ControlPolicy.primary(last_state,
        score_session.is_ready(),score_session.score_error))

func pause() -> void:
    _apply_control(ControlPolicy.pause_toggle(last_state,score_session.score_error))

func retry() -> void:
    _apply_control(ControlPolicy.retry(last_state,score_session.is_ready()))

func listen() -> void:
    _apply_control(ControlPolicy.listen_toggle(last_state))

func _apply_control(decision: Dictionary) -> void:
    if decision.has("message"):
        practice_view.present_message(str(decision["message"]))
    elif decision.has("action"):
        request_action(decision,last_state)

func open_library_piece(identifier: String, resume_saved := false) -> void:
    # Preserve the latest selection while navigation's asynchronous pause
    # is pending; opening is dispatched only after its acknowledgement.
    if state.pending:
        state.queue_library(identifier,resume_saved)
        library_open_status.emit("Preparing your selected music…")
        return
    library_open_status.emit("Opening score…")
    state.resume_requested = resume_saved
    request_command("library.open",{"id":identifier})

func correct_fingering(source_id: String, finger: Variant) -> void:
    var decision: Dictionary = score_session.fingering_correction_request(
        source_id,finger,last_state,state.pending)
    if not bool(decision.get("accepted",false)):
        fingering_save_error = str(decision.get("message","Score not ready"))
        present_fingering_status()
        return
    fingering_save_error = ""
    request_command(str(decision["operation"]),decision["payload"])

func present_fingering_status() -> void:
    var issues: int = practice_view.stage.renderer.annotations.fingering_placement_issues.size() \
        if score_session.is_ready() else 0
    practice_view.stage.present_fingering(
        last_state.get("fingering",{}),issues,fingering_save_error)

func _flush_transport_action() -> void:
    var action: String = state.take_transport()
    if not action.is_empty():
        request_action({"action":action},last_state)

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
    # Send only the readiness owner's source-bound physical measurement;
    # the command handler must never select a renderer or infer the score's
    # geometry from the view tree.
    if action in ["start","restart","resume","score_ready"]:
        var clearance: Dictionary = score_session.continuation_geometry()
        if not clearance.is_empty():
            command = command.duplicate()
            command.merge(clearance,true)
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
        present_fingering_status()
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
        var message := Reply.failure_message(code,body)
        if operation == "fingering.correct":
            fingering_save_error = message
            present_fingering_status()
        var queued_library_failed: bool = state.discard_library()
        command_failure_presenter.present(
            message,operation,queued_library_failed)
        _flush_transport_action()
        return
    var opened: Variant = Reply.decode_reply(body) if operation == "library.open" else null
    if operation in ["learning.export","learning.delete_piece","learning.delete_learner"]:
        var result: Variant = Reply.decode_reply(body)
        learning_accepted.emit(operation,
            result if result is Dictionary else {})
    var decision: Dictionary = CommandSuccessPolicy.decide(
        operation,str(completed["action"]),bool(completed["resume_saved"]),opened)
    if str(decision["kind"]) == "fingering":
        fingering_save_error = ""
        present_fingering_status()
    elif str(decision["kind"]) == "library_open":
        score_session.score_error = ""
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
