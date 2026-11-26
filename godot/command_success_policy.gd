extends RefCounted
## Success classification only. The command coordinator applies completion
## effects, score publication and deferred library selection.
static func decide(path: String, resume_saved: bool,
        opened: Variant = null, outcome: Dictionary = {}) -> Dictionary:
    var kind := "other"
    var open_mode := "none"
    if path == "fingering.correct":
        kind = "fingering"
    elif path == "practice.command":
        kind = "control"
    elif path == "library.health.start":
        kind = "library_health"
    elif path == "sight_reading.start":
        kind = "library_open"
        open_mode = "practice"
        resume_saved = true
    elif path == "library.open":
        kind = "library_open"
        if opened is Dictionary:
            if int(opened.get("lesson_step",1)) > 1:
                open_mode = "resume_choice"
            else:
                open_mode = "practice" if resume_saved else "picker"
    elif path == "settings.update":
        kind = "settings"
    elif path == "midi.device.select":
        kind = "device"
    var effects: Dictionary = outcome.get("effects",{}) \
        if kind == "control" else {}
    return {
        "kind": kind,
        "invalidate_lesson": kind == "control" and
            bool(effects.get("invalidate_lesson",false)),
        "refresh_settings": (kind == "control" and
            bool(effects.get("refresh_settings",false)))
            or kind in ["settings","device"],
        "refresh_library": kind == "settings",
        "navigate_practice": (kind == "control" and
            bool(effects.get("navigate_practice",false)))
            or (kind == "library_open" and open_mode in ["practice","resume_choice"]),
        "publish_state": kind in ["fingering","control"] or
            (kind == "library_open" and
             (open_mode == "resume_choice" or
              (open_mode == "practice" and resume_saved))),
        "resume_saved": resume_saved,
        "open_mode": open_mode,
    }
