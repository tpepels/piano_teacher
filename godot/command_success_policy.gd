extends RefCounted
## Success classification only. Main owns request sequencing, transport
## command completion, score publication, and deferred library selection.
const GUIDED_NAVIGATION := ["skip_stage", "place_original", "revisit_trouble"]
const CALIBRATION_ACTIONS := ["calibration_apply", "calibration_reset"]

static func decide(path: String, action: String,
        resume_saved: bool, opened: Variant = null) -> Dictionary:
    var kind := "other"
    var open_mode := "none"
    if path == "fingering.correct":
        kind = "fingering"
    elif path == "practice.command":
        kind = "control"
    elif path == "library.health.start":
        kind = "library_health"
    elif path == "library.open":
        kind = "library_open"
        if opened is Dictionary:
            open_mode = ("practice" if bool(opened.get("warmup",false))
                or resume_saved else "picker")
    elif path == "settings.update":
        kind = "settings"
    elif path == "midi.device.select":
        kind = "device"
    return {
        "kind": kind,
        "invalidate_lesson": kind == "control" and action == "reset_path",
        "refresh_settings": (kind == "control" and action in CALIBRATION_ACTIONS)
            or kind in ["settings","device"],
        "refresh_library": kind == "settings",
        "navigate_practice": (kind == "control" and action in GUIDED_NAVIGATION)
            or (kind == "library_open" and open_mode == "practice"),
        "publish_state": kind in ["fingering","control"] or
            (kind == "library_open" and open_mode == "practice" and resume_saved),
        "open_mode": open_mode,
    }
