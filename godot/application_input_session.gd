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
var _last_midi_input_count := -1
var _last_midi_phase := ""
var _last_midi_revision := -1

func configure(practice, library) -> void:
    _practice = practice
    _library = library
    _practice.midi_start_suppression_requested.connect(suppress_midi_start)

## A UI modal only suppresses a stale input count. The actual hardware note
## remains owned by Python MidiIngress; this controller observes accepted
## snapshots to turn a fresh keyboard gesture into the existing Play command.
func suppress_midi_start(input_count: int) -> void:
    _last_midi_input_count = input_count

func observe_midi_state(state: Dictionary, sampled: bool, screen: String,
        busy: bool, score_ready: bool) -> void:
    var count: int = int(state.get("midi_input_count",0))
    var phase: String = str(state.get("phase",""))
    var revision: int = int(state.get("revision",-1))
    var fresh: bool = _last_midi_input_count >= 0 and \
        count > _last_midi_input_count
    var stable: bool = _last_midi_phase == phase and \
        _last_midi_revision == revision
    _last_midi_input_count = count
    _last_midi_phase = phase
    _last_midi_revision = revision
    if not fresh or not stable or not sampled or screen != "practice" or \
            busy or not score_ready or _practice.is_source_picker_open() or \
            str(state.get("device","")).is_empty():
        return
    var idle: bool = phase in ["ready","performance_complete","guided_complete"]
    var retry: bool = phase == "feedback" and \
        str(state.get("mode","")) == "practice" and \
        not bool(state.get("auto",false))
    if not idle and not retry:
        return
    if str(state.get("mode","")) == "learn":
        primary_requested.emit()
    elif retry:
        command_requested.emit({"action":"restart"})
    elif str(state.get("mode","")) in ["practice","perform"]:
        command_requested.emit({"action":"start"})

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
