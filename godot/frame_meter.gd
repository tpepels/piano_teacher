extends RefCounted

# Opt-in Phase 8D frame-interval measurements. These are Godot's delivered
# process-frame intervals, not physical display latency or MIDI timestamps.
# Constant memory and one report per ~second; no per-frame sorting/drawing.
var samples: Array[float] = []
var elapsed := 0.0
var _last_ms := NAN
var _last_world := NAN
var _last_identity := ""
var _wall_intervals: Array[float] = []
var _motion_steps: Array[float] = []
var _motion_speeds: Array[float] = []
var _stationary_frames := 0
var _boundary_frames := 0

func record_motion(at_ms: float, world: float, density: float, identity: String) -> void:
    if is_finite(_last_ms) and at_ms > _last_ms:
        var interval: float = at_ms-_last_ms
        _wall_intervals.append(interval)
        # Do not mix different transport phases, layout scales or score
        # revisions when assessing within-passage movement.
        if identity != _last_identity or not is_finite(world) or not is_finite(_last_world) or density <= 0.0:
            _boundary_frames += 1
        else:
            var step: float = (world-_last_world)*density
            _motion_steps.append(step)
            _motion_speeds.append(step*1000.0/interval)
            if absf(step) < .000001:
                _stationary_frames += 1
    _last_ms = at_ms
    _last_world = world
    _last_identity = identity

func motion_report() -> Dictionary:
    var result: Dictionary = {"wall_interval_samples":_wall_intervals.size(),
        "motion_samples":_motion_steps.size(),"stationary_frames":_stationary_frames,
        "transition_frames_excluded":_boundary_frames}
    if not _wall_intervals.is_empty():
        _wall_intervals.sort()
        result["wall_p95_ms"] = snappedf(_wall_intervals[clampi(
            ceili(_wall_intervals.size()*.95)-1,0,_wall_intervals.size()-1)],.001)
        result["wall_worst_ms"] = snappedf(_wall_intervals[-1],.001)
        var total := 0.0
        for interval in _wall_intervals:
            total += interval
        result["wall_fps"] = snappedf(_wall_intervals.size()*1000.0/total,.01)
    if not _motion_steps.is_empty():
        _motion_steps.sort()
        _motion_speeds.sort()
        result["world_step_min_px"] = snappedf(_motion_steps[0],.001)
        result["world_step_max_px"] = snappedf(_motion_steps[-1],.001)
        result["world_speed_min_px_s"] = snappedf(_motion_speeds[0],.01)
        result["world_speed_max_px_s"] = snappedf(_motion_speeds[-1],.01)
    _wall_intervals.clear()
    _motion_steps.clear()
    _motion_speeds.clear()
    _stationary_frames = 0
    _boundary_frames = 0
    return result

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
    _last_ms = NAN
    _last_world = NAN
    _last_identity = ""
    _wall_intervals.clear()
    _motion_steps.clear()
    _motion_speeds.clear()
    _stationary_frames = 0
    _boundary_frames = 0
