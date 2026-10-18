extends SceneTree

# The camera must preserve every onset and have a continuous derivative
# even when tightly packed short notes precede a longer duration.
var failures: Array[String] = []

func check(ok: bool, message: String) -> void:
    if not ok:
        failures.append(message)
        print("SMOOTH_SCORE_FAIL:", message)

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var Curve = load("res://score_motion_curve.gd")
    check(Curve != null, "Camera easing module parses")
    if Curve == null:
        quit(1)
        return
    var anchors: Array = [
        {"beat":0.0, "x":.08},
        {"beat":.25, "x":.18},
        {"beat":.50, "x":.25},
        {"beat":1.5, "x":.40},
        {"beat":2.5, "x":.53},
        {"beat":3.0, "x":.65}]
    for i in range(anchors.size()-1):
        var x: float = Curve.position(anchors, i, float(anchors[i].beat))
        check(absf(x-float(anchors[i].x)) < .000001,
            "Every engraved notehead remains exactly on its MIDI time")
        var h: float = float(anchors[i+1].beat)-float(anchors[i].beat)
        var last_x: float = float(anchors[i].x)
        for step in range(1, 33):
            var at: float = float(anchors[i].beat) + h*step/32.0
            var projected: float = Curve.position(anchors, i, at)
            check(projected >= last_x - .0000001
                and projected <= float(anchors[i+1].x)+.0000001,
                "Short-note interpolation must never jump backward or overshoot")
            last_x = projected
        check(absf(last_x-float(anchors[i+1].x)) < .000001,
            "Next onset does not lose its precise staff position")
    for i in range(1, anchors.size()-1):
        var crossing: float = float(anchors[i].beat)
        var left_speed: float = Curve.velocity(anchors, i-1, crossing)
        var right_speed: float = Curve.velocity(anchors, i, crossing)
        check(absf(left_speed-right_speed) < .00001,
            "Velocity is continuous at each fast-to-slow rhythmic transition")
    var steady: Array = [
        {"beat":0.0, "x":0.0}, {"beat":1.0, "x":.2},
        {"beat":2.0, "x":.4}]
    check(absf(Curve.position(steady, 0, .5) - .1) < .000001,
        "Already-uniform note timing remains completely linear")
    check(absf(Curve.velocity(steady, 0, .5)-.2) < .000001,
        "Already-uniform sheet retains identical speed")
    var lead_speed: float = Curve.velocity(anchors, 0, 0.0)
    check(absf(lead_speed-Curve.velocity(anchors, 0, .00001)) < .0001,
        "Count-in extrapolation meets the opening note without speed jump")
    print("SMOOTH_SCORE_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
