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
    var spoken: Array[int] = []
    var voice_available := false
    func present(beat: float, bar: int, visible: bool, paused: bool,
            _count_in_beats: float = -1.0) -> void:
        events.append([beat,bar,visible,paused])
    func speak_beat(number: int) -> bool:
        spoken.append(number)
        return voice_available

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
    owner.update({"phase":"feedback","paused":false,"score_queue_next":{},
        "count_in_bar_beats":4},1000,NAN,1000)
    owner.update({"phase":"feedback","paused":false,"score_queue_next":{},
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
    # Five measurement rounds are consecutive. There is exactly one
    # preparation sequence, with an accent on each new round's first tap.
    raw_events.clear()
    owner.calibration_tick_index = -999
    clock.has_backend_offset = false
    for tap_clock in range(44):
        var continuous := {"midi_calibration":{
            "active":true, "beat":float(tap_clock), "bpm":80.0,
            "count_in":4, "ticks":8, "rounds":5}}
        owner.update(continuous,1000,NAN,1000)
    if raw_events.size() != 44:
        failures += 1
    else:
        for tap_clock in range(44):
            var expected_accent := tap_clock == 0 or (
                tap_clock >= 4 and posmod(tap_clock-4,8) == 0)
            if raw_events[tap_clock] != expected_accent:
                failures += 1
                break
    # Speech and visuals follow the existing backend beat and never create
    # an independent timer, repeat on a poll, or speak during real notes.
    practice.stage.count_in.voice_available = true
    count_events.clear()
    practice.stage.count_in.spoken.clear()
    var counting := {"running":true,"transport_id":6,
        "phase":"count_in","count_in_bar_beats":4}
    owner.update(counting,1000,-4.0,1000)
    owner.update(counting,1000,-4.0,1010)
    owner.update(counting,1000,-3.0,1020)
    if practice.stage.count_in.spoken != [1,2] or not count_events.is_empty():
        failures += 1
    owner.update(counting,1000,0.0,1030)
    if count_events.size() != 1:
        failures += 1
    # A resumed transport can have positive graded time while the backend
    # provides a separate negative ungraded count-in beat.
    practice.stage.count_in.spoken.clear()
    var resumed := {"running":true,"transport_id":7,"paused":false,
        "phase":"count_in","bpm":60,"count_in_bar_beats":4,
        "resume_count_in_beat":-4.0}
    owner.update(resumed,1000,NAN,1000)
    owner.update(resumed,1000,NAN,1000)
    owner.update(resumed,1000,NAN,2000)
    if practice.stage.count_in.spoken != [1,2]:
        failures += 1
    # An automatic retry uses the same count syllables, but a new tick key.
    practice.stage.count_in.spoken.clear()
    clock.retry_active = true
    clock.preparing = true
    clock.retry_beat = -4.0
    owner.update({"phase":"feedback","paused":false,"score_queue_next":{},
        "count_in_bar_beats":4},2000,NAN,2000)
    if practice.stage.count_in.spoken != [1]:
        failures += 1
    print("METRONOME_FRAME_FAILURES:",failures)
    quit(0 if failures == 0 else 1)
