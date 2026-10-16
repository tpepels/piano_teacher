extends SceneTree

var failures: Array[String] = []

func check(ok: bool, detail: String) -> void:
    if not ok:
        failures.append(detail)
        print("FRAME_METER_FAIL: ", detail)

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var Meter = load("res://frame_meter.gd")
    check(Meter != null, "Frame meter parses on Godot")
    if Meter == null:
        quit(1)
        return
    var meter = Meter.new()
    check(meter.record_frame(0.0).is_empty(),
        "Synthetic zero-duration smoke steps must never be counted")
    for i in range(59):
        check(meter.record_frame(1.0/60.0).is_empty(),
            "Frame report must not spam every frame")
    var report: Dictionary = meter.record_frame(1.0/60.0)
    check(not report.is_empty(), "Collect one second of frames")
    check(report.get("frames", 0) == 60, "Exactly 60 frames are measured")
    check(absf(float(report.get("fps", 0)) - 60.0) < .2,
        "Mean frame rate should reflect the actual supplied intervals")
    check(absf(float(report.get("p95_frame_ms", 0)) - 16.7) < .2,
        "95th percentile frame interval should match steady 60 FPS")
    check(not bool(report.get("physical_display_latency_measured", true)),
        "Frame intervals cannot infer a physical refresh or display latency")
    check(meter.samples.is_empty(), "Bounded report window clears on emission")
    report = {}
    meter.clear()
    report = meter.record_frame(.05)
    for i in range(48):
        var measured: Dictionary = meter.record_frame(.02)
        if not measured.is_empty():
            report = measured
    check(not report.is_empty(), "Stall window must emit one complete report")
    check(float(report.get("worst_frame_ms", 0)) >= 49.9,
        "A missed frame must appear as a stall")
    check(float(report.get("p95_frame_ms", 0)) >= 19.9,
        "Unsteady frame intervals appear in the latency percentile")
    check(meter.record_frame(INF).is_empty(),
        "Invalid frame intervals are ignored")
    meter.clear()
    check(meter.samples.is_empty() and meter.elapsed == 0.0,
        "Reset releases all timing observations")
    print("FRAME_METER_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
