extends SceneTree
const Coordinator := preload("res://metronome_frame_coordinator.gd")

class Settings:
    extends RefCounted
    var calibration_beat_pulse = null
    var history: Array = []
    func animate_calibration_beat(beat: float, active: bool,
            _bars: int = 12, _count: int = 4) -> void:
        history.append([beat,active])

class CountIn:
    extends RefCounted
    var events: Array = []
    func present(beat: float, bar: int, visible: bool, paused: bool) -> void:
        events.append([beat,bar,visible,paused])

class Stage:
    extends RefCounted
    var count_in := CountIn.new()

class Practice:
    extends RefCounted
    var stage := Stage.new()

class Clock:
    extends RefCounted
    var retry_active := false
    var has_backend_offset := false
    var backend_offset_ms := 0.0
    var preparing := false
    var retry_beat := -1.0
    func retry_preparing(_now: int) -> bool:
        return preparing
    func retry_count_in_beat(_now: int) -> float:
        return retry_beat

var count_events: Array = []
var raw_events: Array = []

func _beat(_now: int) -> float:
    return -3.0

func _count(accent: bool, beat: float) -> void:
    count_events.append([accent,beat])

func _raw(accent: bool) -> void:
    raw_events.append(accent)

func _initialize() -> void:
    var failures := 0
    var settings := Settings.new()
    var practice := Practice.new()
    var clock := Clock.new()
    var owner := Coordinator.new(settings,practice,clock,
        Callable(self,"_beat"),Callable(self,"_count"),Callable(self,"_raw"))
    var calibration := {"midi_calibration":{
        "active":true,"beat":0.0,"bpm":60.0,"round_beats":4,
        "count_in":2,"rounds":1}}
    owner.update(calibration,1000,NAN,1000)
    owner.update(calibration,1000,NAN,1010)
    if raw_events != [true] or settings.history.size() != 2:
        failures += 1
    calibration["midi_calibration"]["beat"] = 1.0
    owner.update(calibration,1000,NAN,1000)
    if raw_events != [true,false]:
        failures += 1
    raw_events.clear()
    clock.retry_active = true
    clock.preparing = true
    owner.update({"phase":"feedback","paused":false,
        "count_in_bar_beats":4},1000,NAN,1000)
    owner.update({"phase":"feedback","paused":false,
        "count_in_bar_beats":4},1000,NAN,1000)
    if raw_events != [false] or practice.stage.count_in.events[-1][0] != -1.0:
        failures += 1
    clock.retry_active = false
    owner.update({},1000,NAN,1000)
    if practice.stage.count_in.events[-1] != [0.0,4,false,false]:
        failures += 1
    owner.update({"running":true,"transport_id":5,
        "count_in_bar_beats":4},1000,-3.0,1000)
    owner.update({"running":true,"transport_id":5,
        "count_in_bar_beats":4},1000,-3.0,1010)
    if count_events != [[false,-3.0]]:
        failures += 1
    owner.update({"running":true,"transport_id":5,"paused":true,
        "count_in_bar_beats":4},1000,-2.0,1020)
    if count_events.size() != 1:
        failures += 1
    owner.update({"running":true,"transport_id":5,
        "count_in_bar_beats":4},1000,-1.0,1030)
    if count_events != [[false,-3.0],[false,-1.0]]:
        failures += 1
    # The backend state was sampled 300ms ago, and the original midpoint
    # estimate still lags 250ms. Exact monotonic origin must place the click
    # at the current on-screen downbeat, with no repeated attack on polls.
    raw_events.clear()
    owner.calibration_tick_index = -999
    clock.has_backend_offset = true
    clock.backend_offset_ms = -900000.0
    var delayed := {"midi_calibration":{
        "active":true,"beat":-.3,"bpm":60.0,"round_beats":4,
        "start_at_ms":1000000.0,"sampled_at_ms":999700.0,
        "count_in":2,"rounds":1}}
    owner.update(delayed,99950,NAN,100000)
    if settings.history[-1][0] != 0.0 or raw_events != [true]:
        failures += 1
    owner.update(delayed,99950,NAN,100050)
    if settings.history[-1][0] < .049 or raw_events != [true]:
        failures += 1
    owner.update(delayed,99950,NAN,101000)
    if absf(float(settings.history[-1][0])-1.0) > .00001 or \
            raw_events != [true,false]:
        failures += 1
    print("METRONOME_FRAME_FAILURES:",failures)
    quit(0 if failures == 0 else 1)
