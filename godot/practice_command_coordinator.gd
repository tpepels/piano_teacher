extends RefCounted
## UI intent and request lifecycle only. No musical scheduling or score
## admission lives here; every timed route uses Python PlaybackCoordinator
## and the one ScoreAdmissionGateway.
const CommandRequestState := preload("res://command_request_state.gd")
const CommandSuccessPolicy := preload("res://command_success_policy.gd")
const StateContract := preload("res://state_contract.gd")
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
    _ui_intent("ui_primary")

func pause() -> void:
    _ui_intent("ui_pause")

func retry() -> void:
    _ui_intent("ui_retry")

func listen() -> void:
    _ui_intent("ui_listen")

func _ui_intent(intent: String) -> void:
    request_action({"action":intent},last_state)

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
        practice_view.present_message(str(decision.get("message","Score not ready")))
        return
    request_command(str(decision["operation"]),decision["payload"])

func _flush_transport_action() -> void:
    var action: String = state.take_transport()
    if not action.is_empty():
        request_action({"action":action},last_state)

func request_action(command: Dictionary, presentation_facts: Dictionary) -> void:
    last_state = presentation_facts
    var action: String = str(command.get("action",""))
    if action.begins_with("ui_") and action not in ["ui_suspend","ui_stop"]:
        # Source-bound gestures carry the physical renderer's revision and
        # readiness. Stop and one-way suspension must survive a stale view.
        command = command.duplicate(true)
        command["score_ready"] = score_session.is_ready()
        command["score_revision"] = score_session.revision
        command["score_fingerprint"] = score_session.source_fingerprint()
        if not score_session.score_error.is_empty():
            command["score_error"] = score_session.score_error
    # The backend-published action is used for local effects only.
    # Python resolves the actual gesture again under its session lock.
    var projected_action := action
    if action.begins_with("ui_"):
        var controls: Dictionary = last_state.get("controls",{})
        var choice: Dictionary = controls.get(action.trim_prefix("ui_"),{})
        projected_action = str(choice.get("action",""))
    # User-requested Stop immediately silences an already scheduled local
    # count-in even when the backend command queue is currently busy.
    # The authoritative Stop transaction is still resolved by Python.
    if action in ["stop","ui_stop"]:
        metronome_frame.cancel_reserved_count_in()
    var previous: String = state.control_action
    if not state.action_requested(action,projected_action):
        if action != "ui_suspend":
            practice_view.begin_action(projected_action if not projected_action.is_empty() else action,previous)
        return
    if action != "ui_suspend":
        practice_view.begin_action(projected_action if not projected_action.is_empty() else action)
    # A displayed label may be stale when the backend resolves this click.
    # Provide physical facts for any raw gesture that *may* start, retry
    # or resume. Python chooses the concrete action under its lock.
    # The metronome consumes only an authorized playback segment.
    if action in ["ui_primary","ui_pause","ui_retry","ui_midi_start",
            "start","restart","resume","score_ready"]:
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
        # A failed unrelated command cannot cancel an existing audible
        # segment. MetronomeFrameCoordinator reconciles its countdown
        # directly from the authorized playback state.
        var message := Reply.failure_message(code,body)
        var queued_library_failed: bool = state.discard_library()
        command_failure_presenter.present(
            message,operation,queued_library_failed)
        _flush_transport_action()
        return
    var opened: Variant = Reply.decode_reply(body) if operation in ["library.open","sight_reading.start"] else null
    if operation in ["learning.export","learning.delete_piece","learning.delete_learner"]:
        var result: Variant = Reply.decode_reply(body)
        learning_accepted.emit(operation,
            result if result is Dictionary else {})
    var accepted_outcome: Dictionary = {}
    var presentation_body: PackedByteArray = body
    if operation == "practice.command":
        var envelope: Variant = Reply.decode_reply(body)
        if (not envelope is Dictionary or
                not envelope.get("state") is Dictionary or
                not envelope.get("outcome") is Dictionary):
            command_failure_presenter.present(
                "Practice command returned no accepted state/outcome",
                operation,false)
            _flush_transport_action()
            return
        # A successful command is not a license to run display or
        # navigation effects before its backend state is accepted. Check
        # the identical generated contract used by the poll inbox first.
        var command_state: Dictionary = envelope["state"]
        var violations: Array[String] = StateContract.problems(command_state)
        if not violations.is_empty():
            command_failure_presenter.present(
                "Practice command returned an invalid state: " +
                "; ".join(violations),operation,false)
            _flush_transport_action()
            return
        accepted_outcome = envelope["outcome"]
        var effects: Variant = accepted_outcome.get("effects")
        var valid_outcome: bool = (
            int(accepted_outcome.get("version",-1)) == 1
            and typeof(accepted_outcome.get("executed")) == TYPE_BOOL
            and typeof(accepted_outcome.get("action")) == TYPE_STRING
            and effects is Dictionary)
        if valid_outcome:
            for name in ["navigate_practice","refresh_settings","invalidate_lesson"]:
                if typeof(effects.get(name)) != TYPE_BOOL:
                    valid_outcome = false
                    break
        if not valid_outcome:
            command_failure_presenter.present(
                "Practice command outcome contract is obsolete",
                operation,false)
            _flush_transport_action()
            return
        presentation_body = JSON.stringify(command_state).to_utf8_buffer()
    var decision: Dictionary = CommandSuccessPolicy.decide(
        operation,bool(completed["resume_saved"]),opened,accepted_outcome)
    if str(decision["kind"]) == "library_open":
        score_session.score_error = ""
    if bool(decision.get("publish_state",false)):
        last_published_control_started_ms = maxi(
            last_published_control_started_ms,int(completed["started_ms"]))
    succeeded.emit(decision,opened,code,presentation_body,
        int(completed["started_ms"]))
    _flush_transport_action()
    refresh_requested.emit()
    var deferred: Dictionary = state.take_library()
    if not str(deferred["piece"]).is_empty():
        library_requested.emit(
            str(deferred["piece"]),bool(deferred["resume_saved"]))
