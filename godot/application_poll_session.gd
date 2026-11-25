extends Node
## One owner for application polling cadence, contextual library refresh,
## and sparse ALSA device discovery. The root scene only wires requests.
## No timer is allowed to authorize a playback take or change backend state.
signal library_requested
signal devices_requested
signal library_health_requested

var state_timer: Timer
var _screen: Callable
var _device: Callable
var _health_running: Callable
var _request
var _inbox
var _commands
var _assets
var _practice

func bind_state_request(request, inbox, commands, assets, practice) -> void:
    _request = request
    _inbox = inbox
    _commands = commands
    _assets = assets
    _practice = practice

func poll() -> void:
    var now_ms: int = Time.get_ticks_msec()
    if not _practice.is_source_picker_open():
        _assets.poll(now_ms)
    if not _inbox.pending and not _commands.state.pending:
        _inbox.begin_request(now_ms)
        # Every poll carries the score's current placement facts, so an
        # automatic transition (the next take, a return to Free) is placed
        # from what is on the staff now, not from the last command's facts.
        if _request.request("state.snapshot",_assets.continuation_geometry()) != OK:
            _inbox.pending = false

func accept_state(state: Dictionary) -> void:
    var live_rate: bool = str(_screen.call()) == "practice" and \
        not str(state.get("device","")).is_empty()
    var interval := .08 if live_rate else .15
    if absf(state_timer.wait_time-interval) > .001:
        state_timer.wait_time = interval

func configure(screen: Callable, device: Callable, health_running: Callable) -> void:
    _screen = screen
    _device = device
    _health_running = health_running
    state_timer = _make_timer(0.15,poll)
    _make_timer(5.0,_request_discovery)
    _make_timer(1.2,_request_health)

func _make_timer(interval: float, callback: Callable) -> Timer:
    var timer := Timer.new()
    timer.wait_time = interval
    timer.autostart = true
    timer.timeout.connect(callback)
    add_child(timer)
    return timer

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
