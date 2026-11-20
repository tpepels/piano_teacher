extends Node
## One owner for application polling cadence, contextual library refresh,
## and sparse ALSA device discovery. The root scene only wires requests.
## No timer is allowed to authorize a playback take or change backend state.
signal state_requested
signal library_requested
signal devices_requested
signal library_health_requested

var state_timer: Timer
var _screen: Callable
var _device: Callable
var _health_running: Callable

func configure(screen: Callable, device: Callable, health_running: Callable) -> void:
    _screen = screen
    _device = device
    _health_running = health_running
    state_timer = _make_timer(0.15,_request_state)
    _make_timer(5.0,_request_discovery)
    _make_timer(1.2,_request_health)

func _make_timer(interval: float, callback: Callable) -> Timer:
    var timer := Timer.new()
    timer.wait_time = interval
    timer.autostart = true
    timer.timeout.connect(callback)
    add_child(timer)
    return timer

func _request_state() -> void:
    state_requested.emit()

func _request_discovery() -> void:
    var screen := str(_screen.call())
    if screen == "home" or screen == "library":
        library_requested.emit()
    # The Python connection manager reconnects a selected device.
    # Re-enumerate ALSA only if discovery can change the visible choice.
    if screen == "settings" or (screen == "practice" and
            str(_device.call()).is_empty()):
        devices_requested.emit()

func _request_health() -> void:
    if str(_screen.call()) == "library" and bool(_health_running.call()):
        library_health_requested.emit()
