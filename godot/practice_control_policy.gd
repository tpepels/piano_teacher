extends RefCounted
## The visible Play/Pause/Retry/Listen decisions are pure facts -> commands.
## Main sends the command and presents messages; backend remains authoritative.
const ACTIVE_PHASES := [
    "count_in", "playing", "paused", "feedback", "recovering",
    "loading", "preview_gap"]
const NOTATION_WAIT := "Preparing sheet music - wait for the notes before starting"

static func active_transport(state: Dictionary) -> bool:
    return bool(state.get("running",false)) or \
        str(state.get("phase","")) in ACTIVE_PHASES

static func primary(state: Dictionary, score_ready: bool,
        score_error: String) -> Dictionary:
    var paused: bool = bool(state.get("paused",false))
    if paused and not score_error.is_empty():
        return {"message":score_error}
    var mode: String = str(state.get("mode","practice"))
    if mode == "listen" and not active_transport(state):
        return {"action":"practice" if bool(state.get("warmup",false)) else "listen"}
    if mode == "learn":
        var phase: String = str(state.get("phase","ready"))
        if phase not in ["paused","guided_wait","loading"] and not score_ready:
            return {"message":NOTATION_WAIT}
        var teaching: Dictionary = state.get("teaching",{}) if state.get("teaching") is Dictionary else {}
        if (phase == "guided_complete" and bool(teaching.get("has_more_units",false))
                and not bool(state.get("guided_recovery",false))):
            return {"action":"learn_next"}
        if phase == "paused":
            return {"action":"resume"}
        if phase in ["guided_complete","disconnected"]:
            return {"action":"practice"}
        if phase in ["guided_wait","loading"]:
            return {"action":"pause"}
        return {"action":"learn_retry"}
    if paused:
        return {"action":"resume"}
    if active_transport(state):
        return {"action":"pause"}
    if not bool(state.get("running",false)) and not score_ready:
        return {"message":NOTATION_WAIT}
    return {"action":"pause" if bool(state.get("running",false)) else "start"}

static func pause_toggle(state: Dictionary, score_error: String) -> Dictionary:
    if bool(state.get("paused",false)) and not score_error.is_empty():
        return {"message":score_error}
    if (active_transport(state) or
            (str(state.get("mode","practice")) == "learn"
            and str(state.get("phase","")) in ["guided_wait","paused"])):
        return {"action":"resume" if bool(state.get("paused",false)) else "pause"}
    return {}

static func retry(state: Dictionary, score_ready: bool) -> Dictionary:
    if not score_ready:
        return {}
    return {"action":"learn_retry" if str(state.get("mode","practice")) == "learn"
            else "restart"}

static func listen_toggle(state: Dictionary) -> Dictionary:
    if str(state.get("mode","")) == "listen":
        return {"action":"practice","wait_for_player":true}
    return {"action":"listen"}
