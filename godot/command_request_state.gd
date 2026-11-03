extends RefCounted
## Owns only the outstanding command and deferred user intent.
## No application, retained request adapter, clock sampling or scene tree.
var pending := false
var post_path := ""
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

func begin(path: String, now_ms: int) -> bool:
    if pending:
        return false
    pending = true
    post_path = path
    started_ms = now_ms
    return true

func dispatch(adapter, path: String, payload: Dictionary) -> int:
    ## Dispatch only a request previously reserved by begin(). The adapter
    ## is supplied for this call, never retained or obtained from Main.
    assert(pending and post_path == path)
    adapter.timeout = 360.0 if path in [
        "fingering.correct","library.open","library.open"] else 5.0
    var err: int = int(adapter.request(path,payload))
    if err != OK:
        request_failed()
    return err

func request_failed() -> void:
    pending = false

func finish() -> Dictionary:
    var metadata := {
        "path": post_path,
        "action": control_action,
        "started_ms": started_ms,
        "resume_saved": post_path == "library.open" and resume_requested,
    }
    pending = false
    if post_path == "library.open":
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
