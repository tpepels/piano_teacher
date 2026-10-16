extends RefCounted

# Opt-in Phase 8D frame-interval measurements. These are Godot's delivered
# process-frame intervals, not physical display latency or MIDI timestamps.
# Constant memory and one report per ~second; no per-frame sorting/drawing.
var samples: Array[float] = []
var elapsed := 0.0

func record_frame(delta: float) -> Dictionary:
    if not is_finite(delta) or delta <= 0.0 or delta > 1.0:
        return {}
    elapsed += delta
    samples.append(delta * 1000.0)
    # Avoid 60 identical 1/60-second frames summing infinitesimally
    # below 1.0 because of floating-point representation.
    if elapsed < 1.0 - .000001:
        return {}
    var ordered: Array[float] = samples.duplicate()
    ordered.sort()
    var total := 0.0
    for sample in samples:
        total += sample
    var frame_count: int = samples.size()
    var p95_index: int = clampi(ceili(float(frame_count) * .95) - 1, 0, frame_count - 1)
    var report := {
        "interval_source": "Godot _process delta",
        "frames": frame_count,
        "observed_s": snappedf(elapsed, .001),
        "fps": snappedf(float(frame_count) / elapsed, .1),
        "mean_frame_ms": snappedf(total / float(frame_count), .1),
        "p95_frame_ms": snappedf(ordered[p95_index], .1),
        "worst_frame_ms": snappedf(ordered[-1], .1),
        "physical_display_latency_measured": false}
    samples.clear()
    elapsed = 0.0
    return report

func clear() -> void:
    samples.clear()
    elapsed = 0.0
