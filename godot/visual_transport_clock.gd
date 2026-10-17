extends RefCounted

# Presentation clock; the backend alone scores MIDI and schedules Listen.
# HTTP snapshots contain sampling/transport error. Once an authoritative
# snapshot establishes the origin, project at its BPM until a transport
# transition. Backend and frontend use the same machine's monotonic time;
# chasing poll phase error introduces audible/visible tempo modulation.
const DISCONTINUITY_BEATS := 0.8

var initialized := false
var transport_id := -1
var revision := -1
var bpm := 60.0
var active := false
var beat := 0.0
var last_ms := 0
var backend_offset_ms := 0.0
var best_round_trip_ms := INF
var has_backend_offset := false

func matches(state: Dictionary) -> bool:
    return initialized and transport_id == int(state.get("transport_id", 0)) \
        and revision == int(state.get("revision", -1)) \
        and active == (bool(state.get("running", false)) and not bool(state.get("paused", false))) \
        and absf(bpm - float(state.get("bpm", 60.0))) < 0.001

func now(now_ms: int) -> float:
    if not initialized or not active:
        return beat
    var elapsed: float = maxf(0.0, float(now_ms - last_ms) / 1000.0)
    if elapsed <= 0.0:
        return beat
    beat += elapsed * bpm / 60.0
    last_ms = now_ms
    return beat

func accept(state: Dictionary, measured_ms: int, received_ms: int) -> void:
    var next_bpm: float = maxf(1.0, float(state.get("bpm", 60.0)))
    var next_active: bool = bool(state.get("running", false)) and not bool(state.get("paused", false))
    var next_id: int = int(state.get("transport_id", 0))
    var next_revision: int = int(state.get("revision", -1))
    var captured_ms: int = mini(measured_ms, received_ms)
    if state.has("clock_sampled_at_ms"):
        var backend_ms: float = float(state.clock_sampled_at_ms)
        var round_trip: float = maxf(0.0, 2.0 * (received_ms - captured_ms))
        # Calibrate clock epochs on the lowest-latency idle sample, before
        # the attempt. A delayed first active response then cannot shift its
        # origin. Freeze this offset while moving; never alter musical speed.
        if not has_backend_offset or (not next_active and round_trip < best_round_trip_ms):
            backend_offset_ms = float(captured_ms) - backend_ms
            best_round_trip_ms = round_trip
            has_backend_offset = true
        captured_ms = mini(roundi(backend_ms + backend_offset_ms), received_ms)
    var observed: float = float(state.get("clock_beat", 0.0))
    if next_active:
        observed += float(received_ms - captured_ms) * next_bpm / 60000.0
    var new_session: bool = (not initialized or transport_id != next_id
        or revision != next_revision or active != next_active or absf(bpm - next_bpm) >= 0.001)
    if not new_session:
        now(received_ms)
    var error: float = observed - beat
    # Pausing, retrying and changing tempo are authoritative discontinuities.
    # Huge differences are also explicit seeks, not network jitter.
    if new_session or absf(error) > DISCONTINUITY_BEATS:
        beat = observed
    elif not next_active:
        beat = observed
    initialized = true
    transport_id = next_id
    revision = next_revision
    bpm = next_bpm
    active = next_active
    last_ms = received_ms
