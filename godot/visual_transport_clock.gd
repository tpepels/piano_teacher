extends RefCounted
## The running take's source beat for presentation (count-in clicks after
## the downbeat, note lighting, the playhead clock). During a run it is read
## from the musical timeline the take was placed on, the same mapping Python
## grades with; otherwise it is the backend's published clock_beat.
## Also supplies the exact Godot ms - Python monotonic ms offset.

var score_flow
# Python monotonic ms (PianoNative); set by the score admission gateway.
var backend_clock: Callable
var backend_offset_ms := 0.0
var has_backend_offset := false
var _state: Dictionary = {}
var _sampled_local_ms := 0.0

func _measure_offset() -> void:
    if has_backend_offset or not backend_clock.is_valid():
        return
    var before_us := Time.get_ticks_usec()
    var backend_now: float = float(backend_clock.call())
    var after_us := Time.get_ticks_usec()
    if is_finite(backend_now):
        backend_offset_ms = float(before_us+after_us)*.0005-backend_now
        has_backend_offset = true

func accept(state: Dictionary, _measured_ms: int, received_ms: int) -> void:
    _measure_offset()
    _state = state
    _sampled_local_ms = float(state["clock_sampled_at_ms"])+backend_offset_ms \
        if has_backend_offset and state.has("clock_sampled_at_ms") else float(received_ms)

func matches(state: Dictionary) -> bool:
    return not _state.is_empty() and \
        int(_state.get("transport_id",-1)) == int(state.get("transport_id",-2)) and \
        bool(state.get("running",false))

## Beats since the take's opening beat (negative during its count-in).
func score_beat(at_ms: int) -> float:
    var timeline: Variant = _state.get("playback_timeline")
    var current: Variant = timeline.get("current") if timeline is Dictionary else null
    if score_flow != null and current is Dictionary:
        var beat: float = score_flow.take_beat(str(current.get("segment_id","")),at_ms)
        if is_finite(beat):
            var source: Dictionary = current.get("source",{})
            return beat+float(source.get("from_beat",0.0))- \
                float(_state.get("play_from_beat",0.0))
    var observed: float = float(_state.get("clock_beat",0.0))
    if not bool(_state.get("running",false)) or bool(_state.get("paused",false)):
        return observed
    return observed+(float(at_ms)-_sampled_local_ms)/60000.0* \
        maxf(1.0,float(_state.get("bpm",60.0)))
