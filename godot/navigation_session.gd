extends RefCounted
## Single owner of application navigation state, back routes and screen
## publication. Main constructs screens and wires action/readiness signals;
## changing a screen never independently starts or retimes a graded take.
const NavigationPolicy := preload("res://navigation_policy.gd")

signal suspend_requested
signal library_requested
signal settings_requested
signal devices_requested

var current_screen := "practice"
var settings_return_screen := "practice"
var _backdrop
var _drawer
var _practice
var _library
var _settings
var _screens: Dictionary = {}

func configure(backdrop, drawer, practice, library, settings,
               screens: Dictionary) -> void:
    _backdrop = backdrop
    _drawer = drawer
    _practice = practice
    _library = library
    _settings = settings
    _screens = screens

func update_frame_rate(state: Dictionary) -> void:
    # Display cadence follows the visible context, independently of the
    # backend MIDI/audio timeline and the canonical score projection.
    var active: bool = current_screen == "practice" and bool(state.get("loaded",false))
    active = active or (current_screen == "calibration" and bool(
        state.get("midi_calibration",{}).get("active",false)))
    var target_fps: int = 60 if active else 30
    OS.low_processor_usage_mode = not active
    if Engine.max_fps != target_fps:
        Engine.max_fps = target_fps

func navigate(destination: String, state: Dictionary) -> void:
    if _practice == null or _drawer == null or _screens.is_empty():
        push_error("NAVIGATION_SESSION: screen composition is not ready")
        return
    var decision: Dictionary = NavigationPolicy.plan(destination,current_screen)
    var target: String = str(decision["target"])
    var previous: String = str(decision["previous"])
    if bool(decision["remember_settings"]):
        settings_return_screen = previous
    if bool(decision["suspend"]) and bool(state.get("loaded",false)):
        suspend_requested.emit()
    current_screen = target
    if _backdrop != null:
        _backdrop.visible = target == "practice"
    update_frame_rate(state)
    _drawer.present(target,previous)
    _practice.set_active(target == "practice")
    for screen in _screens:
        var name: String = str(screen)
        # Exactly one screen is drawn. Leaving Practice suspends the
        # session, so its score must not keep painting behind another page.
        (_screens[screen] as Control).visible = name == target
    if target == "library":
        library_requested.emit()
        _library.call_deferred("focus_search")
    elif target == "settings":
        _settings.begin_editing(state)
        settings_requested.emit()
        devices_requested.emit()

