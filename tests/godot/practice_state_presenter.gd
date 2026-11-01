extends SceneTree
const Presenter := preload("res://practice_state_presenter.gd")

class Renderer:
    extends RefCounted
    var annotations = {"fingering_placement_issues":[]}

class Stage:
    extends RefCounted
    var renderer = Renderer.new()
    var fingering: Variant
    func present_fingering(summary, _issues: int, _error: String) -> void:
        fingering = summary

class Practice:
    extends RefCounted
    var stage = Stage.new()
    var reports := 0
    var starts := 0
    var busy_calls := 0
    func present(_state: Dictionary, _ready: bool, _busy: bool,
            _audio_error: bool) -> void:
        reports += 1
    func present_busy(_busy: bool) -> void:
        busy_calls += 1
    func consider_piano_start(_sampled: bool, _practice: bool) -> void:
        starts += 1

class Settings:
    extends RefCounted
    var calibrations := 0
    var practice_reports := 0
    func present_calibration(_values: Dictionary, _offset: int) -> void:
        calibrations += 1
    func present_practice(_state: Dictionary, _selected: bool) -> void:
        practice_reports += 1

class Lesson:
    extends RefCounted
    var reports := 0
    func present_context(_state: Dictionary, _busy: bool) -> void:
        reports += 1

class Session:
    extends RefCounted
    var calls := 0
    func update_context(_state: Dictionary, _now_ms: int) -> void:
        calls += 1

class Effects:
    extends RefCounted
    var marks: Array = []

func _initialize() -> void:
    var failures := 0
    var practice := Practice.new()
    var settings := Settings.new()
    var lesson := Lesson.new()
    var session := Session.new()
    var effects := Effects.new()
    var timer := Timer.new()
    var presenter = Presenter.new(practice,settings,lesson,session,effects,timer)
    var state = {"loaded":true,"phase":"playing","device":"Piano",
        "fingering":{"source":"current"},
        "feedback_marks":[{"id":"note-1","status":"correct"}]}
    presenter.present(state,"practice",false,true,"",false,true,1234,false)
    if lesson.reports!=1 or practice.reports!=1 or practice.starts!=1 or \
            settings.calibrations!=1 or settings.practice_reports!=1 or \
            session.calls!=1 or timer.wait_time!=.08 or effects.marks.size()!=1:
        failures += 1
    var unloaded = {"loaded":false,"phase":"ready","device":""}
    presenter.present(unloaded,"settings",true,false,"",false,false,1300,false)
    if practice.reports!=2 or practice.starts!=1 or session.calls!=2 or \
            timer.wait_time!=.15 or effects.marks.size()!=1:
        failures += 1
    print("PRACTICE_STATE_PRESENTER_FAILURES:",failures)
    timer.free()
    quit(0 if failures==0 else 1)
