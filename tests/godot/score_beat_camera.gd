extends SceneTree

const BeatCamera := preload("res://score_beat_camera.gd")
var failures: Array[String] = []

func check(condition: bool, message: String) -> void:
    if not condition:
        failures.append(message)
        push_error(message)

func _initialize() -> void:
    call_deferred("_run")

func _fixture(rate: float = 96.0) -> Dictionary:
    var anchors: Array = []
    for beat in [0.0, 1.0, 2.0, 3.0, 6.0]:
        anchors.append({"beat": beat, "x": (120.0 + beat * rate) / 1200.0,
            "page": 0, "system": "continuous"})
    return {"widths": [1200.0], "pages": 1, "beats": 6.0,
        "anchors": anchors, "strip_time_proportional": true,
        "strip_timing_fallback": ""}

func _run() -> void:
    var fixture: Dictionary = _fixture()
    var ready: Dictionary = BeatCamera.prepare(fixture)
    check(bool(ready.get("enabled", false)), "Valid Verovio beat-grid enables the fixed camera")
    check(absf(float(ready.get("pixels_per_beat", 0.0)) - 96.0) < .0001,
        "Source pixel density is an actual engraver coordinate")
    var fixed := 600.0
    var scale := .75
    for bpm in [40.0, 80.0, 120.0]:
        var prior := INF
        for frame in range(301):
            var elapsed: float = frame / 60.0
            var clock: float = elapsed * bpm / 60.0 - 3.0
            var x: float = BeatCamera.camera_x(ready, clock, 0.0, fixed, scale)
            if frame > 0:
                var expected: float = ready.pixels_per_beat * scale * bpm / 3600.0
                check(absf((prior - x) - expected) < .0005,
                    "Camera moves at exactly one pixel distance per beat")
            prior = x
        # Negative count-in and the first note have identical camera slope.
        var pre := BeatCamera.camera_x(ready, -.01, 0, fixed, scale)
        var at := BeatCamera.camera_x(ready, 0, 0, fixed, scale)
        var post := BeatCamera.camera_x(ready, .01, 0, fixed, scale)
        check(absf((pre - at) - (at - post)) < .0001,
            "No camera velocity discontinuity at beat zero")
        var seek: float = BeatCamera.camera_x(ready, -.5, 2.0, fixed, scale)
        var equivalent: float = BeatCamera.camera_x(ready, 1.5, 0.0, fixed, scale)
        check(absf(seek - equivalent) < .0001,
            "Seeking uses the same musical beat as unbroken transport")
        var paused: float = BeatCamera.camera_x(ready, 1.5, 0.0, fixed, scale)
        check(absf(paused - equivalent) < .0001,
            "Pausing at an identical clock beat freezes the exact same camera")
    var jitter: Dictionary = _fixture()
    jitter["anchors"][2]["x"] += 15.0 / 1200.0
    var rejected := BeatCamera.prepare(jitter)
    check(not bool(rejected.get("enabled", false)),
        "Non-proportional Verovio positions must fall back, not silently drift")
    var malformed: Dictionary = _fixture()
    malformed["anchors"].append({"beat": 2.0, "x": 0.8, "page": 0})
    check(not bool(BeatCamera.prepare(malformed).get("enabled", false)),
        "Conflicting simultaneous notes must reject the aligned camera")
    var outlier: Dictionary = _fixture()
    outlier["strip_timing_fallback"] = "Extreme short interval"
    check(not bool(BeatCamera.prepare(outlier).get("enabled", false)),
        "Previously detected extreme MIDI ornament retains Verovio fallback")
    var natural: Dictionary = _fixture()
    natural["strip_time_proportional"] = false
    check(not bool(BeatCamera.prepare(natural).get("enabled", false)),
        "Native unstretched engraving cannot masquerade as a beat grid")
    print("SCORE_BEAT_CAMERA_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
