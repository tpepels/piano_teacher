extends RefCounted
## Pure screen-transition decisions. Main retains command dispatch, UI state
## and the currently selected workspace; this policy has no scene references.

const TRANSPORT_PHASES := [
    "count_in", "playing", "guided_wait", "feedback",
    "recovering", "loading", "preview_gap"
]
const START_ACTIONS := [
    "start", "restart", "resume", "score_ready",
    "learn", "learn_retry", "practice", "listen", "perform"
]

static func plan(target: String, previous: String, phase: String,
        action_pending: bool, post_path: String,
        control_action: String) -> Dictionary:
    if target == "home":
        target = "practice"
    var beginning: bool = action_pending and post_path == "practice.command" \
        and control_action in START_ACTIONS
    return {
        "target": target,
        "previous": previous,
        "remember_settings": target == "settings" and previous != "settings",
        "pause": previous == "practice" and target != "practice" and \
            (phase in TRANSPORT_PHASES or beginning),
    }
