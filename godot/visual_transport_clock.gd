extends RefCounted

# Presentation-only phase-locked musical clock.
# Python remains authoritative for MIDI timestamps, assessment and Listen audio.
# HTTP updates may have variable transit latency; accepting every new beat as
# a fresh screen position causes a visible backward/forward camera jitter.
# This clock instead runs at the selected BPM, with a bounded (<= 6%) rate
# adjustment toward the most recent backend sample. No camera easing is used.
const MAX_SLEW_FRACTION := 0.06
const FOLLOW_GAIN := 0.45
const DISCONTINUITY_BEATS := 0.8

var initialized := false
var transport_id := -1
var revision := -1
var bpm := 60.0
var active := false
var beat := 0.0
var last_ms := 0
var sample_beat := 0.0
var sample_ms := 0

func matches(state: Dictionary) -> bool:
    return initialized and transport_id == int(state.get("transport_id", 0)) \
        and revision == int(state.get("revision", -1)) \
        and active == (bool(state.get("running", false)) and not bool(state.get("paused", false))) \
        and absf(bpm - float(state.get("bpm", 60.0))) < 0.001

func _reference_at(now_ms: int) -> float:
    if not active:
        return sample_beat
    var elapsed: float = maxf(0.0, float(now_ms - sample_ms) / 1000.0)
    return sample_beat + elapsed * bpm / 60.0

func now(now_ms: int) -> float:
    if not initialized or not active:
        return beat
    var elapsed: float = maxf(0.0, float(now_ms - last_ms) / 1000.0)
    if elapsed <= 0.0:
        return beat
    var nominal: float = bpm / 60.0
    var error: float = _reference_at(last_ms) - beat
    var correction: float = clampf(error * FOLLOW_GAIN,
        -nominal * MAX_SLEW_FRACTION, nominal * MAX_SLEW_FRACTION)
    # Even after a slow frame or a late HTTP reply, the score advances
    # monotonically, at most six percent either side of the chosen tempo.
    beat += elapsed * (nominal + correction)
    last_ms = now_ms
    return beat

func accept(state: Dictionary, measured_ms: int, received_ms: int) -> void:
    var next_bpm: float = maxf(1.0, float(state.get("bpm", 60.0)))
    var next_active: bool = bool(state.get("running", false)) and not bool(state.get("paused", false))
    var next_id: int = int(state.get("transport_id", 0))
    var next_revision: int = int(state.get("revision", -1))
    var captured_ms: int = mini(measured_ms, received_ms)
    var captured_beat: float = float(state.get("clock_beat", 0.0))
    var observed: float = captured_beat
    if next_active:
        observed += float(received_ms - captured_ms) * next_bpm / 60000.0
    var new_session: bool = (not initialized or transport_id != next_id
        or revision != next_revision or active != next_active or absf(bpm - next_bpm) >= 0.001)
    if not new_session:
        now(received_ms)
    # A changed attempt, pause/resume or tempo is a real discontinuity.
    # Handle it explicitly rather than trying to animate through stale music.
    if new_session or absf(beat - observed) > DISCONTINUITY_BEATS:
        beat = observed
    elif not next_active:
        beat = observed
    initialized = true
    transport_id = next_id
    revision = next_revision
    bpm = next_bpm
    active = next_active
    last_ms = received_ms
    sample_beat = captured_beat
    sample_ms = captured_ms
