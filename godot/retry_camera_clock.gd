extends RefCounted
## Single immutable timeline for retry camera and metronome count-in.
## Poll snapshots establish one deadline; later HTTP jitter never reanchors it.
## The score renderer remains source-based; this is presentation-only.

var active := false
var revision := -1
var source_transport := -1
var playing_transport := -1
var deadline_ms := 0.0
var preparation_start_ms := 0.0
var rewind_origin_ms := 0.0
var rewind_origin_beat := 0.0
var rewind_speed := 0.0
var start_beat := 0.0
var end_beat := 0.0
var beats_per_second := 0.0

func reset() -> void:
    active = false
    playing_transport = -1

func accept(state: Dictionary, sampled_ms: int) -> void:
    var phase := str(state.get("phase", ""))
    var retry_phase := phase in ["feedback", "recovering"]
    var next_revision := int(state.get("revision", -1))
    var next_transport := int(state.get("transport_id", -1))
    if active and next_revision == revision and phase == "playing" \
            and (next_transport == source_transport + 1 or
                 next_transport == playing_transport):
        playing_transport = next_transport
        return
    if (active and retry_phase and
            (next_revision != revision or next_transport != source_transport
             or playing_transport >= 0)):
        # A later failed take starts an entirely new, fixed retry trajectory.
        reset()
    elif not retry_phase:
        # Unrelated transport starts (manual Play, seek, another score) must
        # never inherit the previous retry camera.
        reset()
    var preparation: Variant = state.get("practice_preparation")
    if not retry_phase or not preparation is Dictionary \
            or not (str(preparation.get("phase", "")) in ["reverse", "preparing"]):
        return
    if active:
        return
    var measure: Variant = preparation.get("measure")
    if not measure is Dictionary:
        return
    var remaining := float(state.get("transition_in_seconds", 0.0))
    if remaining <= 0.0:
        return
    var bpm := maxf(1.0, float(state.get("bpm", 60.0)))
    beats_per_second = bpm / 60.0
    start_beat = float(measure.get("start_beat", 0.0))
    end_beat = float(measure.get("end_beat", 0.0))
    deadline_ms = float(sampled_ms) + remaining * 1000.0
    preparation_start_ms = deadline_ms - (end_beat-start_beat) / beats_per_second * 1000.0
    rewind_origin_ms = float(sampled_ms)
    rewind_origin_beat = float(state.get("visual_scroll_beat", 0.0))
    var reverse_time := preparation_start_ms-rewind_origin_ms
    rewind_speed = ((start_beat-rewind_origin_beat) * 1000.0/reverse_time
                    if reverse_time > 1.0 else 0.0)
    source_transport = next_transport
    playing_transport = -1
    revision = next_revision
    active = true

func beat_at(now_ms: int) -> float:
    if not active:
        return NAN
    var now := float(now_ms)
    if now < preparation_start_ms:
        return (clampf(rewind_origin_beat + rewind_speed *
                (now-rewind_origin_ms)/1000.0,
                minf(rewind_origin_beat, start_beat),
                maxf(rewind_origin_beat, start_beat)))
    # Forward through the preparation measure and directly onto the first
    # attack. No snapshot snap, temporary pause, or speed modulation.
    return start_beat + (now-preparation_start_ms)/1000.0 * beats_per_second

func count_in_beat(now_ms: int) -> float:
    return (float(now_ms)-deadline_ms)/1000.0 * beats_per_second

func is_preparing(now_ms: int) -> bool:
    return active and float(now_ms) >= preparation_start_ms
