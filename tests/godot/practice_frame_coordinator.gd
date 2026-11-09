extends SceneTree
const Coordinator := preload("res://practice_frame_coordinator.gd")

class Busy:
    extends RefCounted
    var calls := 0
    func present_busy(_busy: bool) -> void:
        calls += 1

class Effects:
    extends RefCounted
    var last_beat := NAN
    func sync_beat(beat: float, _meter: int, _ungraded: bool) -> void:
        last_beat = beat

class Renderer:
    extends RefCounted
    var runway_origin_beat := 0.0
    var last_beat := NAN
    var last_visual := NAN
    var flow_world := NAN
    var flow_calls := 0
    func present_flow(world: float, _state: Dictionary,
            _beat: float) -> void:
        flow_calls += 1
        flow_world = world
    func present_clock(beat: float, visual: float) -> void:
        last_beat = beat
        last_visual = visual

class Stage:
    extends RefCounted
    var renderer = Renderer.new()
    var runway_steps = null
    var effects = Effects.new()

class Practice:
    extends RefCounted
    var stage = Stage.new()
    var calls := 0
    func present_busy(_busy: bool) -> void:
        calls += 1

class Session:
    extends RefCounted
    var checks := 0
    func ensure_current(_ticks: int) -> void:
        checks += 1

class Demo:
    extends RefCounted
    var loaded := true
    var started := false
    var synchronized := NAN
    var kept := NAN
    func synchronize(_state: Dictionary, beat: float) -> void:
        synchronized = beat
        started = true
    func keep_synchronized(beat: float, _bpm: float, _segments: Array) -> void:
        kept = beat

func _initialize() -> void:
    var failures := 0
    var settings := Busy.new()
    var practice := Practice.new()
    var lesson := Busy.new()
    var session := Session.new()
    var demo := Demo.new()
    var coordinator = Coordinator.new(practice,settings,lesson,session,demo,null)
    var empty: Dictionary = {}
    if not coordinator.advance(empty,1.25,9.25,1000,.016,
            false,"practice",true,[]).is_empty():
        failures += 1
    if settings.calls != 1 or practice.calls != 1 or lesson.calls != 1:
        failures += 1
    if practice.stage.renderer.flow_calls != 1 or \
            practice.stage.renderer.flow_world != 9.25:
        # An unloaded/empty score must still receive the one moving bar.
        failures += 1

    var state := {"mode":"listen","running":true,"paused":false,
        "loaded":true,"transport_id":7,"play_from_beat":0.0}
    coordinator.last_strike_transport = 7
    coordinator.last_strike_beat = 1.0
    coordinator.advance(state,1.25,9.25,1016,.016,false,"practice",true,[])
    if settings.calls != 1 or practice.calls != 1 or lesson.calls != 1:
        failures += 1
    coordinator.advance(state,1.25,9.25,1032,.016,true,"practice",true,[])
    if settings.calls != 2 or practice.calls != 2 or lesson.calls != 2:
        failures += 1
    if demo.synchronized != 1.25 or demo.kept != 1.25 or \
            practice.stage.renderer.flow_calls != 3 or \
            practice.stage.renderer.flow_world != 9.25 or \
            practice.stage.renderer.last_beat != 1.25 or \
            practice.stage.renderer.last_visual != 9.25 or \
            practice.stage.effects.last_beat != 1.25 or \
            coordinator.last_strike_beat != 1.25 or session.checks != 3:
        failures += 1
    var paused_state := state.duplicate(true)
    paused_state["phase"] = "paused"
    paused_state["paused"] = true
    coordinator.advance(paused_state,1.25,9.25,1048,.016,
        false,"practice",true,[])
    if practice.stage.renderer.flow_calls != 4 or \
            practice.stage.renderer.flow_world != 9.25:
        failures += 1
    coordinator.advance(state,1.25,10.25,1064,.016,
        false,"practice",true,[])
    if practice.stage.renderer.flow_calls != 5 or \
            practice.stage.renderer.flow_world != 10.25:
        failures += 1
    print("PRACTICE_FRAME_COORDINATOR_FAILURES:",failures)
    quit(0 if failures==0 else 1)
