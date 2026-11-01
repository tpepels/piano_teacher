extends SceneTree
const Effects := preload("res://command_success_effects.gd")
const Policy := preload("res://command_success_policy.gd")

class Presenter:
    extends RefCounted
    var events: Array
    func _init(ordered: Array) -> void:
        events = ordered
    func present_accepted(decision: Dictionary) -> void:
        events.append("present:" + str(decision["kind"]))
    func present_source_picker(_opened: Dictionary) -> void:
        events.append("picker")

var events: Array = []

func _state(_result: int, _code: int, _headers: PackedStringArray,
        _body: PackedByteArray, started_ms: int) -> void:
    events.append("state:" + str(started_ms))

func _navigate(screen: String) -> void:
    events.append("navigate:" + screen)

func _settings() -> void:
    events.append("settings")

func _library() -> void:
    events.append("library")

func _health() -> void:
    events.append("health")

func _score() -> void:
    events.append("score")

func _initialize() -> void:
    var failures := 0
    var presenter := Presenter.new(events)
    var handler := Effects.new(presenter, Callable(self,"_state"),
        Callable(self,"_navigate"), Callable(self,"_settings"),
        Callable(self,"_library"), Callable(self,"_health"),
        Callable(self,"_score"))
    var headers := PackedStringArray()
    var body := PackedByteArray()
    var cases: Array = [
        ["/control","calibration_apply",false,null,
            ["present:control","settings","state:37"]],
        ["/control","skip_stage",false,null,
            ["present:control","state:37","navigate:practice"]],
        ["/library/open","",true,{"warmup":false},
            ["present:library_open","navigate:practice","state:37","score"]],
        ["/library/open","",false,{"warmup":true},
            ["present:library_open","navigate:practice","score"]],
        ["/library/open","",false,{"warmup":false},
            ["present:library_open","picker"]],
        ["/settings","",false,null,
            ["present:settings","settings","library"]],
        ["/device","",false,null,
            ["present:device","settings"]],
        ["/library/health","",false,null,
            ["present:library_health","health"]],
        ["/fingering","",false,null,
            ["present:fingering","state:37"]],
    ]
    for entry in cases:
        events.clear()
        var decision: Dictionary = Policy.decide(
            str(entry[0]),str(entry[1]),bool(entry[2]),entry[3])
        handler.apply(decision,entry[3],0,200,headers,body,37)
        if events != entry[4]:
            failures += 1
            print("FAIL_SUCCESS_EFFECTS:",entry[0],entry[1],events,entry[4])
    print("COMMAND_SUCCESS_EFFECTS_FAILURES:",failures)
    quit(0 if failures==0 else 1)
