extends RefCounted
## Single owner of application navigation state, back routes and screen
## publication. Main constructs screens and wires action/readiness signals;
## changing a screen never independently starts or retimes a graded take.
const NavigationPolicy := preload("res://navigation_policy.gd")

signal pause_requested
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
var _lesson
var _screens: Dictionary = {}
var _frame_rate: Callable

func configure(backdrop, drawer, practice, library, settings, lesson,
               screens: Dictionary, frame_rate: Callable) -> void:
    _backdrop = backdrop
    _drawer = drawer
    _practice = practice
    _library = library
    _settings = settings
    _lesson = lesson
    _screens = screens
    _frame_rate = frame_rate

func navigate(destination: String, state: Dictionary, pending) -> void:
    if _practice == null or _drawer == null or _screens.is_empty():
        push_error("NAVIGATION_SESSION: screen composition is not ready")
        return
    var command = pending
    var decision: Dictionary = NavigationPolicy.plan(
        destination,current_screen,str(state.get("phase","")),
        command.pending,command.operation,command.control_action)
    var target: String = str(decision["target"])
    var previous: String = str(decision["previous"])
    if bool(decision["remember_settings"]):
        settings_return_screen = previous
    if bool(decision["pause"]):
        pause_requested.emit()
    current_screen = target
    if _backdrop != null:
        _backdrop.visible = target == "practice"
    if _frame_rate.is_valid():
        _frame_rate.call(state)
    _drawer.present(target,previous)
    _practice.set_active(target == "practice")
    for screen in _screens:
        var name: String = str(screen)
        (_screens[screen] as Control).visible = (
            name == target or name == "practice" and target != "practice")
    if target == "library":
        library_requested.emit()
        _library.call_deferred("focus_search")
    elif target == "settings":
        _settings.begin_editing(state)
        settings_requested.emit()
        devices_requested.emit()
    elif target == "lesson":
        _lesson.refresh(Time.get_ticks_msec())

func back(state: Dictionary, command) -> void:
    navigate(settings_return_screen if current_screen == "settings"
             else "practice",state,command)
