extends RefCounted
## Owns only the outstanding command and deferred user intent.
## No application, retained request adapter, clock sampling or scene tree.
var pending := false
var operation := ""
var control_action := ""
var started_ms := 0
var queued_transport := ""
var queued_library_piece := ""
var queued_library_resume := false
var resume_requested := false

func action_requested(action: String) -> bool:
    if pending:
        if action in ["pause", "stop"]:
            queued_transport = action
        return false
    control_action = action
    return true

func begin(next_operation: String, now_ms: int) -> bool:
    if pending:
        return false
    pending = true
    operation = next_operation
    if next_operation != "practice.command":
        control_action = ""
    started_ms = now_ms
    return true

func dispatch(adapter, operation_name: String, payload: Dictionary) -> int:
    ## Dispatch only a request previously reserved by begin(). The adapter
    ## is supplied for this call, never retained or obtained from Main.
    assert(pending and operation == operation_name)
    adapter.timeout = 360.0 if operation_name in [
        "fingering.correct", "library.open", "learning.export",
        "learning.delete_piece", "learning.delete_learner"] else 5.0
    var err: int = int(adapter.request(operation_name,payload))
    if err != OK:
        request_failed()
    return err

func request_failed() -> void:
    pending = false
    operation = ""
    control_action = ""
    started_ms = 0
    resume_requested = false

func finish() -> Dictionary:
    if not pending:
        return {}
    var metadata := {
        "operation": operation,
        "action": control_action,
        "started_ms": started_ms,
        "resume_saved": operation == "library.open" and resume_requested,
    }
    pending = false
    operation = ""
    control_action = ""
    started_ms = 0
    resume_requested = false
    return metadata

func take_transport() -> String:
    var action := queued_transport
    queued_transport = ""
    return action

func queue_library(piece: String, resume_saved: bool) -> void:
    queued_library_piece = piece
    queued_library_resume = resume_saved

func discard_library() -> bool:
    var had_selection := not queued_library_piece.is_empty()
    queued_library_piece = ""
    queued_library_resume = false
    return had_selection

func take_library() -> Dictionary:
    var result := {
        "piece": queued_library_piece,
        "resume_saved": queued_library_resume,
    }
    queued_library_piece = ""
    queued_library_resume = false
    return result
