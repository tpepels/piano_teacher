extends RefCounted
## Owns keyboard capture, modal-first event routing and semantic dispatch.
## The application scene composes signals once and never translates an input
## event into competing musical decisions. The stateless router has no clock.
const Router := preload("res://application_event_router.gd")

signal exit_requested
signal fullscreen_requested
signal navigation_requested(screen: String)
signal advanced_pause_requested
signal primary_requested
signal pause_requested
signal retry_requested
signal listen_requested
signal command_requested(payload: Dictionary)

var _practice
var _library

func configure(practice, library) -> void:
    _practice = practice
    _library = library

func capture(event: InputEvent, screen: String, viewport: Viewport) -> bool:
    if _practice == null or _library == null:
        return false
    if _practice.handle_source_input(event):
        # Source picker owns its own edit keys. It may also receive pointer
        # input via GUI; do not mark non-key events handled on its behalf.
        return false
    var key: InputEventKey = event if event is InputEventKey else null
    var focused: bool = viewport.gui_get_focus_owner() is LineEdit
    var capture_action: String = Router.capture_action(
        event,screen,
        _practice.retains_modal_navigation(key.keycode) if key != null else false,
        focused,_library.is_search_focused())
    if capture_action == "focus_library_search":
        _library.focus_search(true)
        return true
    if capture_action == "keyboard":
        # Presses and releases are both consumed, including release after
        # focused buttons, so no extra GUI accept event is generated.
        dispatch(event,screen,viewport)
        return true
    return false

func dispatch(event: InputEvent, screen: String, viewport: Viewport) -> bool:
    if _practice == null:
        return false
    var key: InputEventKey = event if event is InputEventKey else null
    var effect: Dictionary = Router.command(
        event,screen,_practice.is_source_picker_open(),
        _practice.retains_modal_navigation(key.keycode) if key != null else false,
        viewport.gui_get_focus_owner() is LineEdit)
    if effect.is_empty():
        return false
    match str(effect.get("kind","")):
        "exit":
            exit_requested.emit()
        "fullscreen":
            fullscreen_requested.emit()
        "navigate":
            navigation_requested.emit(str(effect["target"]))
        "advanced_pause":
            advanced_pause_requested.emit()
        "primary":
            primary_requested.emit()
        "pause":
            pause_requested.emit()
        "retry":
            retry_requested.emit()
        "listen":
            listen_requested.emit()
        "command":
            command_requested.emit({"action":str(effect["action"])})
        _:
            return false
    return true
