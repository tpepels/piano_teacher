extends RefCounted

# Presentation clock; the backend alone scores MIDI and schedules Listen.
# Engine snapshots contain sampling/transport error. Once an authoritative
# snapshot establishes the origin, project at its BPM until a transport
# transition. Backend and frontend use the same machine's monotonic time;
# chasing poll phase error introduces audible/visible tempo modulation.
const DISCONTINUITY_BEATS := 0.8
const TempoTimeline := preload("res://tempo_timeline.gd")

var initialized := false
var transport_id := -1
var revision := -1
var bpm := 60.0
var tempo_segments: Array = []
var timeline_elapsed_seconds := 0.0

func _beat_at_seconds(seconds: float, segments: Array) -> float:
    return TempoTimeline.beat_at_seconds(seconds, bpm, segments)

func _uniform_tempo(segments: Array, nominal: float) -> bool:
    # Constant-BPM maps still contain one or more explicit source segments.
    # They remain compatible with the same epoch through the appended rest.
    for entry in segments:
        if absf(float(entry.get("bpm", nominal)) - nominal) > 0.001:
            return false
    return true

var active := false
var beat := 0.0
var last_ms := 0
var backend_offset_ms := 0.0
var best_round_trip_ms := INF
var has_backend_offset := false

# Exactly one presentation owner for all transport phases. Reversal,
# preparation, and playback are different segments of this same clock.
# The backend alone controls MIDI assessment, source BPM and the deadline.
var retry_active := false
var retry_revision := -1
var retry_transport := -1
var retry_playing_transport := -1
var retry_start_ms := 0.0
var retry_preparation_ms := 0.0
var retry_deadline_ms := 0.0
var retry_from_beat := 0.0
var retry_start_beat := 0.0
var retry_velocity := 0.0
var retry_bpm := 60.0
var retry_visual_offset := 0.0
var retry_play_from := 0.0
var idle_visual_beat := 0.0
var idle_visual_speed := 0.0
var idle_visual_target := 0.0
var idle_continues_through_gap := false
var idle_visual_sample_ms := 0
var active_visual_offset := 0.0
var active_play_from := 0.0
var source_phase := ""

# A forward pass and its following automatic rest are one monotonic
# schedule. Rendering consumes the same backend run_at epoch as MIDI grading,
# rather than re-anchoring the camera from each delayed state reply.
var visual_epoch_enabled := false
var visual_epoch_backend_ms := 0.0
var visual_epoch_offset_beats := 0.0
var visual_epoch_bpm := 60.0
var visual_epoch_segments: Array = []

func _visual_from_epoch(at_ms: int) -> float:
    var elapsed: float = (float(at_ms) - backend_offset_ms -
        visual_epoch_backend_ms) / 1000.0
    return visual_epoch_offset_beats + TempoTimeline.beat_at_seconds(
        elapsed, visual_epoch_bpm, visual_epoch_segments)

func _accept_retry(state: Dictionary, sampled_ms: int) -> void:
    var phase := str(state.get("phase", ""))
    var ident := int(state.get("transport_id", -1))
    var rev := int(state.get("revision", -1))
    var in_recovery := phase in ["feedback", "recovering"]
    if retry_active and phase == "playing" and rev == retry_revision \
            and (ident == retry_transport + 1 or ident == retry_playing_transport):
        retry_playing_transport = ident
        retry_visual_offset = float(state.get("visual_offset_beats", retry_visual_offset))
        retry_play_from = float(state.get("play_from_beat", retry_play_from))
        return
    if not in_recovery or (retry_active and
            (rev != retry_revision or ident != retry_transport or retry_playing_transport >= 0)):
        retry_active = false
    if not in_recovery or retry_active:
        return
    var preparation: Variant = state.get("practice_preparation")
    if not preparation is Dictionary or not (str(preparation.get("phase", "")) in ["reverse", "preparing"]):
        return
    var measure: Variant = preparation.get("measure")
    if not measure is Dictionary:
        return
    var remaining := float(state.get("transition_in_seconds", 0.0))
    if remaining <= 0.0:
        return
    retry_revision = rev
    retry_transport = ident
    retry_playing_transport = -1
    retry_start_ms = float(sampled_ms)
    retry_deadline_ms = retry_start_ms + remaining * 1000.0
    retry_bpm = maxf(1.0, float(state.get("bpm", 60.0)))
    retry_start_beat = float(measure.get("start_beat", 0.0))
    var destination: float = float(measure.get("end_beat", 0.0))
    retry_preparation_ms = retry_deadline_ms - (destination-retry_start_beat)*60000.0/retry_bpm
    retry_from_beat = float(state.get("visual_scroll_beat", 0.0))
    var rewind_duration: float = retry_preparation_ms - retry_start_ms
    retry_velocity = ((retry_start_beat-retry_from_beat)*1000.0/rewind_duration
        if rewind_duration > 1.0 else 0.0)
    retry_visual_offset = float(state.get("visual_offset_beats", 0.0))
    retry_play_from = float(state.get("play_from_beat", 0.0))
    retry_active = true

func visual_beat(at_ms: int) -> float:
    if retry_active and source_phase in ["feedback", "recovering", "playing"]:
        if float(at_ms) < retry_preparation_ms:
            return clampf(retry_from_beat +
                (float(at_ms)-retry_start_ms)/1000.0 * retry_velocity,
                minf(retry_from_beat, retry_start_beat),
                maxf(retry_from_beat, retry_start_beat))
        return retry_start_beat + (float(at_ms)-retry_preparation_ms)/60000.0 * retry_bpm
    if visual_epoch_enabled and (active or idle_continues_through_gap):
        return _visual_from_epoch(at_ms)
    if active:
        return active_visual_offset + active_play_from + now(at_ms)
    var projected: float = idle_visual_beat + idle_visual_speed * \
        maxf(0.0, float(at_ms-idle_visual_sample_ms)/1000.0)
    # The final measure of an automatic attempt is already the count-in for
    # the next copy. Godot may see the Python transition up to a poll or an
    # engraving/assessment stall later. Do not freeze the score at the exact
    # rest boundary while awaiting that reply. Both copies share this axis.
    # Explicit Stop/Pause and non-automatic feedback still stop at target.
    if idle_continues_through_gap and idle_visual_speed > 0.0:
        return projected
    return minf(idle_visual_target, projected) if idle_visual_speed > 0.0 \
        else maxf(idle_visual_target, projected)

func retry_count_in_beat(at_ms: int) -> float:
    return (float(at_ms)-retry_deadline_ms)/60000.0*retry_bpm

func retry_preparing(at_ms: int) -> bool:
    return retry_active and float(at_ms) >= retry_preparation_ms \
        and float(at_ms) < retry_deadline_ms

func score_beat(at_ms: int) -> float:
    # Both the scrolling score and its fixed playhead use this same epoch.
    if retry_active and source_phase == "playing":
        return visual_beat(at_ms) - retry_visual_offset - retry_play_from
    if visual_epoch_enabled and active:
        return _visual_from_epoch(at_ms) - active_visual_offset - active_play_from
    return now(at_ms)


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
    if tempo_segments.is_empty():
        beat += elapsed * bpm / 60.0
    else:
        timeline_elapsed_seconds += elapsed
        beat = _beat_at_seconds(timeline_elapsed_seconds, tempo_segments)
    last_ms = now_ms
    return beat

func accept(state: Dictionary, measured_ms: int, received_ms: int) -> void:
    source_phase = str(state.get("phase", ""))
    active_visual_offset = float(state.get("visual_offset_beats", 0.0))
    active_play_from = float(state.get("play_from_beat", 0.0))
    idle_visual_beat = float(state.get("visual_scroll_beat",
        active_visual_offset+active_play_from))
    idle_visual_speed = float(state.get("visual_scroll_speed", 0.0))
    idle_visual_target = float(state.get("visual_target_beat",idle_visual_beat))
    idle_continues_through_gap = (not bool(state.get("paused", false))
        and source_phase in ["feedback", "preview_gap"]
        and (bool(state.get("auto", false)) or bool(state.get("preview_only", false)))
        and float(state.get("visual_scroll_speed", 0.0)) > 0.0)
    idle_visual_sample_ms = measured_ms
    _accept_retry(state, measured_ms)
    var next_bpm: float = maxf(1.0, float(state.get("bpm", 60.0)))
    var next_active: bool = bool(state.get("running", false)) and not bool(state.get("paused", false))
    var next_id: int = int(state.get("transport_id", 0))
    var next_revision: int = int(state.get("revision", -1))
    var next_segments: Array = state.get("tempo_segments", [])
    var captured_ms: int = mini(measured_ms, received_ms)
    if state.has("clock_sampled_at_ms"):
        var backend_ms: float = float(state.clock_sampled_at_ms)
        var round_trip: float = maxf(0.0, 2.0 * (received_ms - captured_ms))
        # Calibrate clock epochs on the lowest-latency idle sample, before
        # the attempt. A delayed first active response then cannot shift its
        # origin. Freeze this offset while moving; never alter musical speed.
        if not has_backend_offset or (not next_active and
                absf(idle_visual_speed) < 0.000001 and
                not retry_active and round_trip < best_round_trip_ms):
            backend_offset_ms = float(captured_ms) - backend_ms
            best_round_trip_ms = round_trip
            has_backend_offset = true
        captured_ms = mini(roundi(backend_ms + backend_offset_ms), received_ms)
    # The explicit forward visual map contains authored tempo changes and
    # the appended silent measure at practice BPM. This is the exact same
    # run_at timeline used to grade MIDI; the rest is no special clock state.
    # Old snapshots lacking the field retain the strictly limited fallback.
    var has_visual_map: bool = state.has("visual_tempo_segments")
    visual_epoch_enabled = (state.has("visual_run_at_ms") and
        has_backend_offset and (has_visual_map or next_active or
            _uniform_tempo(next_segments, next_bpm)))
    if visual_epoch_enabled:
        visual_epoch_backend_ms = float(state.get("visual_run_at_ms", 0.0))
        visual_epoch_offset_beats = active_visual_offset + active_play_from
        visual_epoch_bpm = next_bpm
        # Active graded time includes source tempo changes. Automatic gap
        # transport uses the same source-time mapping until its next take.
        visual_epoch_segments = state.get("visual_tempo_segments",
            next_segments).duplicate(true)
    var observed: float = float(state.get("clock_beat", 0.0))
    var next_elapsed: float = float(state.get("clock_elapsed_seconds", 0.0))
    if next_active:
        if next_segments.is_empty():
            observed += float(received_ms - captured_ms) * next_bpm / 60000.0
        else:
            # Backend sends the same tempo segments and sampled elapsed
            # seconds. Extrapolate through the segment boundary, not at one BPM.
            var old_bpm := bpm
            bpm = next_bpm
            observed = _beat_at_seconds(next_elapsed+
                float(received_ms-captured_ms)/1000.0, next_segments)
            bpm = old_bpm
    var new_session: bool = (not initialized or transport_id != next_id
        or revision != next_revision or active != next_active
        or tempo_segments != next_segments or absf(bpm - next_bpm) >= 0.001)
    if not new_session:
        now(received_ms)
    var error: float = observed - beat
    # Pausing, retrying and changing tempo are authoritative discontinuities.
    # Huge differences are also explicit seeks, not network jitter.
    if new_session or absf(error) > DISCONTINUITY_BEATS:
        beat = observed
        timeline_elapsed_seconds = (next_elapsed+
            float(received_ms-captured_ms)/1000.0 if next_active else next_elapsed)
    elif not next_active:
        beat = observed
    initialized = true
    transport_id = next_id
    revision = next_revision
    bpm = next_bpm
    tempo_segments = next_segments.duplicate(true)
    active = next_active
    last_ms = received_ms
