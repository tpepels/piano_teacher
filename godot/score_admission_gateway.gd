extends Node
## Draws each timed take where the musical timeline placed it.
## Python places every take (count-in, rest, take) on one timeline and
## starts it; this adapter only puts the take's notes at its world start on
## the matching renderer, binds them to the take for feedback, and reserves
## the count-in. Nothing is negotiated: a take whose start has already passed
## the playhead, or whose renderer never becomes ready, is reported as a
## display failure and Python stops it.
const Request := preload("res://inprocess_request.gd")

signal admission_problem(message: String)

# Accepted snapshots a running take may wait for its renderer.
const MAX_UNPLACED_FRAMES := 240

var bus: Node
var stage
var score_session
var runway
var flow
var musical_clock
var metronome
var failure_request: Node
var placed_segment := ""
# Takes first seen after their opening note passed (a stalled frame),
# reported so Python places them again.
var late_takes_reported := 0
var missing_score_frames := 0
var unplaced_frames := 0
var reported_failure_segment := ""
var failure_report_in_flight := ""
var _missing_segment := ""
var _unplaced_segment := ""
var _last_problem := ""
var _last_problem_ms := -100000

func last_problem() -> String:
    """The most recent display problem reported to the learner."""
    return _last_problem

func _report_problem(message: String) -> void:
    var now_ms: int = Time.get_ticks_msec()
    if message != _last_problem or now_ms-_last_problem_ms > 5000:
        _last_problem = message
        _last_problem_ms = now_ms
        admission_problem.emit(message)


func configure(host: Node, bridge: Node, practice_stage,
        score_assets, score_runway, score_flow, clock, count_in) -> void:
    bus = bridge
    stage = practice_stage
    score_session = score_assets
    runway = score_runway
    flow = score_flow
    musical_clock = clock
    metronome = count_in
    flow.backend_clock = Callable(self,"_backend_ms")
    musical_clock.backend_clock = Callable(self,"_backend_ms")
    failure_request = Request.new()
    failure_request.timeout = 8.0
    host.add_child(failure_request)
    failure_request.configure(bus)
    failure_request.request_completed.connect(_failure_reported)

func _backend_ms() -> float:
    if bus == null or bus.native == null:
        return NAN
    # Same std::chrono::steady_clock epoch as Python time.monotonic.
    return float(bus.native.call("monotonic_milliseconds"))

func _report_authorized_failure(take_id: String, segment_id: String,
        reason: String) -> void:
    # The Python coordinator alone decides to stop the take.
    if (segment_id.is_empty() or take_id.is_empty()
            or reported_failure_segment == segment_id
            or failure_request.is_pending()):
        return
    var payload := {"take_id":take_id,
        "segment_id":segment_id,"reason":reason}
    # Replacement must measure the ink that is actually retained NOW,
    # not reuse the command snapshot that failed. Python validates the
    # failed take identity before accepting these revision-bound facts.
    if score_session != null:
        var placement: Dictionary = score_session.continuation_geometry()
        if not placement.is_empty():
            payload["placement"] = placement
    if failure_request.request("playback.failure",payload) == OK:
        reported_failure_segment = segment_id
        failure_report_in_flight = segment_id

static func _identity(state: Dictionary, current: Dictionary) -> Dictionary:
    var source: Dictionary = current.get("source",{})
    return {"fingerprint":str(source.get("fingerprint","")),
        "revision":int(source.get("revision",-1)),
        "stage_key":str(source.get("stage_key","")),
        "hand":str(source.get("hand","")),
        "mode":str(state.get("mode",""))}

func _matching_renderer(identity: Dictionary):
    if score_session != null and score_session.matches_ready_source(identity):
        return stage.renderer
    return null

static func _assets_cover_window(view, state: Dictionary) -> bool:
    # The renderer must hold the selected window (including a cross-bar
    # release), never another window that merely shares its opening beat.
    var source_timing: Dictionary = state.get("practice_timeline",{})
    return (absf(view.timeline.duration_beats -
            float(source_timing.get("source_duration_beats",-1.0))) <= 0.0001
            and absf(view.timeline.sounding_duration_beats -
                float(source_timing.get("sounding_duration_beats",-1.0))) <= 0.0001)

static func _timeline_take(state: Dictionary, segment_id: String) -> Dictionary:
    var published: Variant = state.get("musical_timeline")
    if not published is Dictionary:
        return {}
    for segment in published.get("segments",[]):
        if str(segment.get("kind","")) == "take" and \
                str(segment.get("take_id","")) == segment_id:
            return segment
    return {}

func observe(state: Dictionary, _frame_ms: int) -> void:
    var timeline: Variant = state.get("playback_timeline")
    var current: Variant = timeline.get("current") if timeline is Dictionary else null
    var running: bool = bool(state.get("running",false))
    if not running or bool(state.get("paused",false)) or not current is Dictionary:
        unplaced_frames = 0
        return
    var segment_id: String = str(current.get("segment_id",""))
    if segment_id != _unplaced_segment:
        _unplaced_segment = segment_id
        unplaced_frames = 0
    if segment_id.is_empty():
        return
    if segment_id == placed_segment:
        _check_bound_segment(state,timeline,current,segment_id)
        return
    var outcome: String = _place(state,current,segment_id)
    if outcome == "placed":
        placed_segment = segment_id
        unplaced_frames = 0
        return
    unplaced_frames += 1
    # A take first seen after its opening note passed can never be drawn:
    # Python places it again at once. Otherwise give the renderer time.
    if outcome == "passed" or unplaced_frames >= MAX_UNPLACED_FRAMES:
        _late_or_missing(current,segment_id,outcome == "passed")

func _late_or_missing(current: Dictionary, segment_id: String, late: bool) -> void:
    if reported_failure_segment == segment_id or failure_request.is_pending():
        return
    if not late:
        _report_problem("The score for this take could not be drawn")
    _report_authorized_failure(str(current.get("take_id","")),segment_id,
        "timeline_take_not_drawn")
    if late and reported_failure_segment == segment_id:
        late_takes_reported += 1
        print("LATE_SCORE_REPLACEMENT_REQUESTED segment=",segment_id)

func _check_bound_segment(state: Dictionary, timeline: Dictionary,
        current: Dictionary, segment_id: String) -> void:
    if segment_id != _missing_segment:
        _missing_segment = segment_id
        missing_score_frames = 0
    var confirmed: bool = bool(timeline.get("presentation_confirmed",true))
    # Judge expiry using the sampled backend clock, not a stale count-in poll.
    if not confirmed and float(state.get("clock_sampled_at_ms",0.0)) >= \
            float(current.get("deadline_ms",INF)):
        _late_or_missing(current,segment_id,true)
        return
    var view = stage.renderer
    if confirmed and str(state.get("phase","")) == "playing" and \
            (not is_instance_valid(view) or view.bound_segment_id() != segment_id):
        missing_score_frames += 1
        if missing_score_frames >= 4:
            _report_authorized_failure(str(current.get("take_id","")),segment_id,
                "running_take_without_admitted_source")
    else:
        missing_score_frames = 0

func _place(state: Dictionary, current: Dictionary, segment_id: String) -> String:
    var take: Dictionary = _timeline_take(state,segment_id)
    if take.is_empty() or not flow.following:
        return "wait"
    var now_ms: int = Time.get_ticks_msec()
    var start_world: float = flow.run_world(float(take["world_start"]))
    if start_world <= flow.project(now_ms):
        return "passed"
    var identity: Dictionary = _identity(state,current)
    var view = _matching_renderer(identity)
    if view == null or not is_instance_valid(view) or \
            not _assets_cover_window(view,state):
        return "wait"
    var origin: float = float(view.runway_origin_beat)
    var opening: float = float(take.get("source_from_beat",0.0))
    # The settled timeline is the only source of new visible notation.
    var placed: Dictionary = view.place_timeline_take(
        flow.project(now_ms)-origin,opening,
        start_world-origin,float(current.get("count_in_beats",0.0)))
    if placed.is_empty() or absf(float(placed.get("start_world",NAN))-(start_world-origin)) > .0001:
        _report_problem("Cannot draw the take where the timeline placed it")
        if not placed.is_empty():
            view.cancel_stream_arm()
        return "wait"
    if not view.bind_stream_segment(segment_id) or not view.acknowledge_stream_arm():
        view.cancel_stream_arm()
        return "wait"
    var count_in: float = float(current.get("count_in_beats",0.0))
    if count_in > 0.0:
        var backend_now: float = _backend_ms()
        if is_finite(backend_now):
            var deadline_local: float = float(current["deadline_ms"]) + \
                float(now_ms)-backend_now
            metronome.reserve_count_in(
                deadline_local,float(current.get("bpm",60.0)),count_in,
                current.get("count_in_meter",[4,4]),count_in,"start",
                current.get("count_in_plan",{}),
                str(current.get("take_id","")),segment_id)
            metronome.acknowledge_reserved_count_in(now_ms)
    return "placed"

func _failure_reported(code: int, body: PackedByteArray) -> void:
    if code != 0:
        # An unsuccessful report is not a delivered failure. A later frame
        # may retry this exact source loss if playback remains active.
        if reported_failure_segment == failure_report_in_flight:
            reported_failure_segment = ""
        _report_problem("Could not halt playback after notation loss: "+
            body.get_string_from_utf8())
    failure_report_in_flight = ""
