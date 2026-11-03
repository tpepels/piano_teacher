extends RefCounted
## Apply successful command effects in original request order.
## Dependencies are narrow callables; no scene root or request adapter retained.
var presenter
var publish_state: Callable
var navigate_practice: Callable
var request_settings: Callable
var request_library: Callable
var request_library_health: Callable
var refresh_score: Callable

func _init(view_presenter, on_state: Callable, on_navigate: Callable,
        on_settings: Callable, on_library: Callable, on_health: Callable,
        on_score: Callable) -> void:
    presenter = view_presenter
    publish_state = on_state
    navigate_practice = on_navigate
    request_settings = on_settings
    request_library = on_library
    request_library_health = on_health
    refresh_score = on_score

func apply(decision: Dictionary, opened: Variant,
        code: int, body: PackedByteArray, started_ms: int) -> void:
    presenter.present_accepted(decision)
    match str(decision["kind"]):
        "fingering":
            publish_state.call(code, body, started_ms)
        "control":
            if bool(decision["refresh_settings"]):
                request_settings.call()
            publish_state.call(code, body, started_ms)
            if bool(decision["navigate_practice"]):
                navigate_practice.call("practice")
        "library_health":
            request_library_health.call()
        "library_open":
            match str(decision["open_mode"]):
                "practice":
                    navigate_practice.call("practice")
                    if bool(decision["publish_state"]):
                        # A resumed lesson is restored by backend state,
                        # never by a second open-at request.
                        publish_state.call(code, body, started_ms)
                    refresh_score.call()
                "picker":
                    presenter.present_source_picker(opened)
        "settings":
            if bool(decision["refresh_settings"]):
                request_settings.call()
            if bool(decision["refresh_library"]):
                request_library.call()
        "device":
            if bool(decision["refresh_settings"]):
                request_settings.call()
