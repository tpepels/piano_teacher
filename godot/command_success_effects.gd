extends RefCounted
## Apply successful command effects in original request order.
## Dependencies are narrow callables; no scene root or request adapter retained.
var presenter
signal publish_state(code: int, body: PackedByteArray, started_ms: int)
signal navigate_practice(screen: String)
signal request_settings
signal request_library
signal request_library_health
signal refresh_score

func _init(view_presenter) -> void:
    presenter = view_presenter

func apply(decision: Dictionary, opened: Variant,
        code: int, body: PackedByteArray, started_ms: int) -> void:
    presenter.present_accepted(decision)
    match str(decision["kind"]):
        "fingering":
            publish_state.emit(code, body, started_ms)
        "control":
            if bool(decision["refresh_settings"]):
                request_settings.emit()
            publish_state.emit(code, body, started_ms)
            if bool(decision["navigate_practice"]):
                navigate_practice.emit("practice")
        "library_health":
            request_library_health.emit()
        "library_open":
            match str(decision["open_mode"]):
                "practice":
                    navigate_practice.emit("practice")
                    if bool(decision["publish_state"]):
                        # A resumed lesson is restored by backend state,
                        # never by a second open-at request.
                        publish_state.emit(code, body, started_ms)
                    refresh_score.emit()
                "picker":
                    presenter.present_source_picker(opened)
                "resume_choice":
                    navigate_practice.emit("practice")
                    if bool(decision["publish_state"]):
                        publish_state.emit(code, body, started_ms)
                    refresh_score.emit()
                    presenter.present_resume_choice(opened, not bool(decision.get("resume_saved",false)))
        "settings":
            if bool(decision["refresh_settings"]):
                request_settings.emit()
            if bool(decision["refresh_library"]):
                request_library.emit()
        "device":
            if bool(decision["refresh_settings"]):
                request_settings.emit()
