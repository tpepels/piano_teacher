extends RefCounted

# Phase 8B: pure, bounded Listen audio-to-score drift evaluation.
# Godot's mix clock can estimate software drift, never physical key or
# speaker latency. A transient HTTP poll error must not seek the piano.
const TOLERANCE_SECONDS := 0.20
const REQUIRED_CONSECUTIVE := 3
const CORRECTION_COOLDOWN_MS := 1800
const START_GUARD_SECONDS := 0.40
const END_GUARD_SECONDS := 0.40

var outliers := 0
var last_correction_ms := -200000
var corrections := 0
var last_error_s := 0.0
var peak_error_s := 0.0

func reset_pending() -> void:
    outliers = 0

func reset_session() -> void:
    outliers = 0
    last_correction_ms = -200000
    corrections = 0
    last_error_s = 0.0
    peak_error_s = 0.0

func evaluate(target_s: float, audible_s: float, duration_s: float,
        now_ms: int) -> bool:
    if not is_finite(target_s) or not is_finite(audible_s) \
            or not is_finite(duration_s) or duration_s <= 0.0 \
            or target_s < START_GUARD_SECONDS \
            or target_s > duration_s - END_GUARD_SECONDS:
        reset_pending()
        return false
    last_error_s = target_s - audible_s
    peak_error_s = maxf(peak_error_s, absf(last_error_s))
    if absf(last_error_s) <= TOLERANCE_SECONDS:
        reset_pending()
        return false
    outliers += 1
    if outliers < REQUIRED_CONSECUTIVE \
            or now_ms - last_correction_ms < CORRECTION_COOLDOWN_MS:
        return false
    last_correction_ms = now_ms
    corrections += 1
    reset_pending()
    return true

func report() -> Dictionary:
    return {
        "software_drift_s": snappedf(last_error_s, .001),
        "peak_software_drift_s": snappedf(peak_error_s, .001),
        "seeks": corrections,
        "threshold_s": TOLERANCE_SECONDS,
        "physical_latency_measured": false}
