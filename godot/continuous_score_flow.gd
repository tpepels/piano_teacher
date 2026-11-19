extends RefCounted
## One forward-only score world, projected from the canonical versioned
## PresentationTimeline. This is the presentation API, not a second clock.
## Native score clipping and score admissions consume the same projection.
const PresentationTimeline := preload("res://presentation_timeline.gd")
var timeline = PresentationTimeline.new()
var beat := 0.0
var last_ms := -1
var bpm := 40.0
var initialized := false
var hold_world := INF

func sample(at_ms: int, selected_bpm: float = NAN) -> float:
    if not initialized:
        timeline.initialize(at_ms,selected_bpm if is_finite(selected_bpm) else bpm)
    elif is_finite(selected_bpm) and selected_bpm > 0.0:
        timeline.set_rate(at_ms,selected_bpm)
    beat = timeline.sample(at_ms)
    last_ms = timeline.last_ms
    bpm = timeline.current_rate()
    initialized = timeline.initialized()
    hold_world = timeline.hold_world
    return beat

func switch_rate_at(at_ms: float, next_bpm: float) -> void:
    # Compatibility for the presentation adapter. A late clock correction
    # can change FUTURE velocity only; it never rewrites exposed positions.
    if not is_finite(at_ms) or not is_finite(next_bpm):
        return
    timeline.set_rate(roundi(maxf(at_ms,float(timeline.last_ms))),next_bpm)
    bpm = timeline.current_rate()

func authorize_source_epoch(deadline_ms: float, opening: float,
        nominal_bpm: float, authored_segments: Array,
        segment_id: String) -> void:
    timeline.authorize_source_epoch(
        deadline_ms,opening,nominal_bpm,authored_segments,segment_id)

func project(at_ms: int) -> float:
    return timeline.project(at_ms)

func hold_at(world: float) -> void:
    timeline.set_hold(world,maxi(0,timeline.last_ms))
    beat = timeline.last_world
    hold_world = timeline.hold_world

func release_hold() -> void:
    if is_finite(timeline.hold_world):
        timeline.set_hold(INF,maxi(0,timeline.last_ms))
    hold_world = timeline.hold_world

func project_authored_future(at_ms: int, sampled_ms: int,
        source_beat: float, nominal_bpm: float,
        authored_segments: Array) -> float:
    # Use the same versioned epoch projector for both actual committed
    # music and candidate authored tempo maps. The candidate remains
    # entirely hypothetical until ScoreAdmissionGateway authorizes it.
    if not timeline.active_segment.is_empty():
        return project(at_ms)
    return timeline.forecast_authored(
        at_ms,sampled_ms,source_beat,nominal_bpm,authored_segments)

func reset() -> void:
    timeline.reset()
    beat = 0.0
    last_ms = -1
    bpm = 40.0
    initialized = false
    hold_world = INF
