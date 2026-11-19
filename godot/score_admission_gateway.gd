extends Node
## Sole physical admission adapter for the authoritative Python PlaybackCoordinator.
## All timed routes arrive as versioned engine intents. The only commit path is
## preview -> arm immutable source -> backend reserve -> confirm presentation.
const Request := preload("res://inprocess_request.gd")
const TransportReservation := preload("res://score_transport_reservation.gd")
const TempoTimeline := preload("res://tempo_timeline.gd")

signal admission_problem(message: String)

var bus: Node
var stage
var score_session
var runway
var flow
var musical_clock
var metronome
var reserve_request: Node
var present_request: Node
var withdraw_request: Node
var failure_request: Node
var status_request: Node
var current: Dictionary = {}
var renderer
var receipt: Dictionary = {}
var admission_state: Dictionary = {}
var started_ms := -1
var pending_reconciliation := false
var last_activated_segment := ""
var last_activated_intent := ""
var last_activated_attempt := -1
var missing_score_frames := 0
var reported_failure_segment := ""
var _last_problem := ""
var _last_problem_ms := -100000

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
    reserve_request = _request(host, Callable(self, "_reserved"))
    present_request = _request(host, Callable(self, "_presented"))
    withdraw_request = _request(host, Callable(self, "_withdrawn"))
    failure_request = _request(host, Callable(self, "_failure_reported"))
    status_request = _request(host, Callable(self, "_status_received"))

func _request(host: Node, callback: Callable) -> Node:
    var call := Request.new()
    call.timeout = 8.0
    host.add_child(call)
    call.configure(bus)
    call.request_completed.connect(callback)
    return call

func _backend_ms() -> float:
    if bus == null or bus.native == null:
        return NAN
    # Same std::chrono::steady_clock epoch as Python time.monotonic on
    # supported Linux builds. No sampled UI/backend offset is used for the
    # transaction's graded deadline.
    return float(bus.native.call("monotonic_milliseconds"))

func _matching_renderer(intent: Dictionary):
    var revision: int = int(intent.get("revision", -1))
    if score_session != null and score_session.is_ready() and \
            str(score_session._fingerprint) == str(intent.get("fingerprint","")) and \
            int(score_session.revision) == revision and \
            int(score_session.rendered_revision) == revision:
        return stage.renderer
    if runway != null and runway._future != null and \
            is_instance_valid(runway._future) and runway._acknowledged and \
            runway._future.retained_ready() and \
            int(runway._bundle.get("revision", -2)) == revision and \
            str(runway._bundle.get("fingerprint","")) == str(intent.get("fingerprint","")) and \
            str(runway._bundle.get("stage_key", "")) == str(intent.get("stage_key", "")):
        # Link ALL outgoing source/rest layers BEFORE computing clearance.
        runway._link_existing_layers(runway._future)
        return runway._future
    return null

func _deadline_at_world(target_world: float, local_ms: int, beat: float,
        bpm: float, segments: Array) -> float:
    # Invert the very same forward source/world projection the renderer
    # uses. A fixed nominal-BPM conversion fails across tempo-map changes.
    var low := 0.0
    var high := 1000.0
    for i in range(22):
        if flow.project_authored_future(local_ms + roundi(high),
                local_ms, beat, bpm, segments) >= target_world:
            break
        high *= 2.0
    if high >= 4194304000.0:
        return NAN
    for i in range(38):
        var mid: float = 0.5 * (low + high)
        if flow.project_authored_future(local_ms + roundi(mid),
                local_ms, beat, bpm, segments) < target_world:
            low = mid
        else:
            high = mid
    return high

func _admit(intent: Dictionary, state: Dictionary, frame_ms: int) -> void:
    var view = _matching_renderer(intent)
    if view == null or not is_instance_valid(view):
        return
    if (str(state.get("piece_fingerprint","")) != str(intent.get("fingerprint",""))
            or int(state.get("revision",-1)) != int(intent.get("revision",-2))):
        return
    var backend_now: float = _backend_ms()
    if not is_finite(backend_now):
        return
    # This is a cross-language epoch consistency check, not a clock
    # estimator. If the native and Python monotonic sources disagree, fail
    # closed rather than silently admitting a take at the wrong time.
    if state.has("clock_sampled_at_ms") and \
            absf(backend_now-float(state["clock_sampled_at_ms"])) > 1800.0:
        _report_problem("Playback clocks disagree; refusing score admission")
        return
    var world: float = flow.project(frame_ms)
    var backend_floor: float = float(intent.get("earliest_deadline_ms", NAN))
    if not is_finite(world) or not is_finite(backend_floor):
        return
    var tempo: float = maxf(1.0, float(state.get("bpm", intent.get("bpm", 40.0))))
    var authored: Array = (
        state.get("tempo_segments", [])
        if bool(state.get("running", false)) and \
            str(state.get("phase", "")) == "playing" else [])
    var delay_ms: float = maxf(0.0, backend_floor-backend_now)+420.0
    var floor_world: float = flow.project_authored_future(
        frame_ms+roundi(delay_ms),frame_ms,
        float(state.get("clock_beat",0.0)),tempo,authored)
    var count_in: float = float(intent.get("count_in_beats", 0.0))
    var required_slot: float = maxf(count_in, floor_world-world)
    var action: String = str(intent.get("action", "start"))
    var reservation_action: String = (
        "resume" if action == "resume" else
        "restart" if action == "restart" else "start")
    var opening: float = float(intent.get("from_beat",0.0))
    var planned: Dictionary = {}
    var partial: float = float(intent.get("resume_remaining_beats",0.0))
    var admitted_floor: float = backend_floor
    if action == "resume" and partial > 0.0:
        # Reuse an already-spoken count-in only when the ORIGINAL unexposed
        # source is still ahead of the playhead. The pure preflight avoids
        # appending a short-count-in source that would restart the music.
        var partial_floor: float = backend_now + \
            TempoTimeline.seconds_from_beats(partial,tempo)*1000.0+420.0
        var partial_world: float = flow.project_authored_future(
            frame_ms+roundi(partial_floor-backend_now),frame_ms,
            float(state.get("clock_beat",0.0)),tempo,authored)
        var partial_slot: float = maxf(partial,partial_world-world)
        var preview: Dictionary = TransportReservation.plan(
            view,"resume",world,opening,partial_slot)
        if bool(preview.get("ok",false)) and \
                str(preview.get("mode","")) == "reuse":
            planned = view.reserve_transport_action(
                "resume",world,opening,partial_slot)
            if not planned.is_empty() and \
                    bool(planned.get("reused_unplayed_count_in",false)):
                admitted_floor = partial_floor
            else:
                if not planned.is_empty():
                    view.cancel_stream_arm()
                planned.clear()
    if planned.is_empty():
        # Every newly inserted source gets its own complete bar. Reuse is
        # the sole exception; the count-in is never silently shortened.
        planned = view.reserve_transport_action(
            reservation_action,world,opening,required_slot)
    if planned.is_empty():
        _report_problem("Cannot reserve source notation for this playback")
        return
    # From this point the gateway owns the provisional source. Any failure
    # in coordinate inversion or deadline validation must cancel that exact
    # arm and restore its safe withdrawn suffix.
    renderer = view
    admission_state = state.duplicate(true)
    current = intent.duplicate(true)
    started_ms = frame_ms
    var start_world: float = float(planned.get("start_world", NAN))
    var lead_ms: float = _deadline_at_world(
        start_world,frame_ms,float(state.get("clock_beat",0.0)),
        tempo,authored)
    if not is_finite(lead_ms):
        _cancel_provisional()
        return
    var deadline: float = backend_now+lead_ms
    if deadline < admitted_floor-.01:
        _cancel_provisional()
        _report_problem("Reserved notation precedes its musical deadline")
        return
    current["deadline_ms"] = deadline
    current["world_origin"] = start_world
    current["reused_count_in"] = bool(
        planned.get("reused_unplayed_count_in", false))
    started_ms = frame_ms
    var payload: Dictionary = {
        "intent_id": str(intent["intent_id"]),
        "attempt": int(intent["attempt"]),
        "take_id": str(intent["take_id"]),
        "fingerprint": str(intent["fingerprint"]),
        "stage_key": str(intent["stage_key"]),
        "revision": int(intent["revision"]),
        "hand": str(intent["hand"]),
        "source_from_beat": opening,
        "deadline_ms": deadline,
        "world_origin": start_world,
        "queue_generation": int(view._stream_serial),
        "renderer_generation": int(intent["revision"]),
        "reused_count_in": bool(current["reused_count_in"]),
    }
    if reserve_request.request("playback.reserve",payload) != OK:
        _cancel_provisional()

func observe(state: Dictionary, frame_ms: int) -> void:
    var intent: Variant = state.get("playback_intent")
    var timeline: Variant = state.get("playback_timeline")
    var pending_segment: String = str(receipt.get("segment_id",""))
    var active_segment: String = (
        str(timeline.get("segment_id",""))
        if timeline is Dictionary else "")
    # A worker can authorize a take before its in-process reply is delivered.
    # The resulting running-state poll is AUTHORITATIVE; never roll back the
    # source just because this poll no longer contains the pending intent.
    if not pending_segment.is_empty() and active_segment == pending_segment:
        pending_reconciliation = false
        _confirm_authorized(timeline)
    if timeline is Dictionary:
        var segment: String = str(timeline.get("segment_id",""))
        if bool(state.get("running", false)) and \
                str(state.get("phase", "")) == "playing" and \
                not segment.is_empty() and \
                stage.renderer != null and \
                stage.renderer._stream_live_segment_id != segment:
            missing_score_frames += 1
            if missing_score_frames >= 4 and reported_failure_segment != segment:
                reported_failure_segment = segment
                if failure_request._pending_id < 0:
                    failure_request.request("playback.failure",{
                        "take_id": str(timeline.get("take_id", "")),
                        "segment_id": segment,
                        "reason": "running_take_without_admitted_source"})
        else:
            missing_score_frames = 0
    var suspended: bool = (bool(state.get("paused",false)) and
        (not intent is Dictionary or
        str(intent.get("action","")) != "resume"))
    if not intent is Dictionary or suspended:
        if not current.is_empty():
            # Never infer a rejected reservation from a missing intent in
            # a possibly newer state snapshot. An outstanding reserve or
            # present command must first finish/reconcile.
            if reserve_request._pending_id >= 0 or \
                    present_request._pending_id >= 0:
                return
            if not receipt.is_empty():
                pending_reconciliation = true
                if status_request._pending_id < 0 and \
                        Time.get_ticks_msec()-started_ms >= 400:
                    started_ms = Time.get_ticks_msec()
                    _query_status()
            elif not pending_reconciliation:
                _cancel_provisional()
        return
    var identifier: String = str(intent.get("intent_id",""))
    var attempt: int = int(intent.get("attempt",-1))
    if identifier == last_activated_intent and attempt == last_activated_attempt:
        return
    if not current.is_empty():
        if str(current.get("intent_id","")) == identifier and \
                int(current.get("attempt",-2)) == attempt:
            if pending_reconciliation and present_request._pending_id < 0 and \
                    reserve_request._pending_id < 0 and \
                    status_request._pending_id < 0 and \
                    Time.get_ticks_msec()-started_ms > 800 and \
                    not receipt.is_empty():
                started_ms = Time.get_ticks_msec()
                _query_status()
            return
        # This is a NEW intent. Reconcile the former reservation before
        # touching its ink, because its result can arrive out of order.
        if reserve_request._pending_id >= 0 or \
                present_request._pending_id >= 0 or \
                status_request._pending_id >= 0:
            return
        if not receipt.is_empty():
            pending_reconciliation = true
            _query_status()
            return
        _cancel_provisional()
    if reserve_request._pending_id >= 0 or present_request._pending_id >= 0:
        return
    _admit(intent,state,frame_ms)

func _reserved(code: int, body: PackedByteArray) -> void:
    if current.is_empty():
        return
    var data: Variant = JSON.parse_string(body.get_string_from_utf8())
    if code != 0 or not data is Dictionary or \
            not bool(data.get("reserved",false)):
        _cancel_provisional()
        _report_problem("Backend rejected notation reservation: "+str(
            data.get("error","invalid receipt") if data is Dictionary else code))
        return
    receipt = data
    if renderer == null or not is_instance_valid(renderer) or \
            not renderer.bind_stream_segment(str(data.get("segment_id",""))) or \
            not renderer.acknowledge_stream_arm():
        _cancel_provisional()
        return
    # Keep the preloaded renderer provisional until the backend confirms
    # authorization. A failed/expired receipt must not replace the visible
    # outgoing stage; promotion is the final local presentation commit.
    _send_presentation()

func _send_presentation() -> void:
    if receipt.is_empty():
        return
    var payload: Dictionary = {
        "intent_id":str(receipt["intent_id"]),
        "attempt":int(receipt["attempt"]),
        "segment_id":str(receipt["segment_id"])}
    if present_request.request("playback.present",payload) != OK:
        pending_reconciliation = true

func _presented(code: int, body: PackedByteArray) -> void:
    var data: Variant = JSON.parse_string(body.get_string_from_utf8())
    if code == 0 and data is Dictionary and \
            bool(data.get("authorized",false)):
        pending_reconciliation = false
        _confirm_authorized(data)
    else:
        # In-process timeouts can lose a response after the backend already
        # committed the transport. Query its transaction ledger first.
        pending_reconciliation = true
        _query_status()

func _query_status() -> void:
    if status_request._pending_id < 0 and not receipt.is_empty():
        status_request.request("playback.status")

func _status_received(code: int, body: PackedByteArray) -> void:
    if not pending_reconciliation or receipt.is_empty():
        return
    if code != 0:
        # No rollback on an uncertain response: the old notation may
        # already be grading. The next state poll retries reconciliation.
        return
    var status: Variant = JSON.parse_string(body.get_string_from_utf8())
    if not status is Dictionary:
        return
    var expected: String = str(receipt.get("segment_id",""))
    if str(status.get("active_segment_id","")) == expected:
        _confirm_authorized(receipt)
        return
    if str(status.get("reserved_segment_id","")) == expected and \
            str(status.get("intent_id","")) == str(receipt.get("intent_id","")) and \
            int(status.get("attempt",-2)) == int(receipt.get("attempt",-1)):
        pending_reconciliation = false
        _send_presentation()
        return
    # Definitively absent from both active and reserved state. The
    # reservation expired or was superseded; its unseen ink can be removed.
    _cancel_provisional()

func _confirm_authorized(data: Dictionary) -> void:
    if receipt.is_empty():
        return
    var expected: String = str(receipt.get("segment_id",""))
    if str(data.get("segment_id","")) != expected:
        return
    if runway != null and renderer != null and \
            is_instance_valid(renderer) and runway._future == renderer:
        if not runway.promote_reserved(admission_state):
            if failure_request._pending_id < 0:
                failure_request.request("playback.failure",{
                    "take_id":str(receipt.get("take_id","")),
                    "segment_id":expected,
                    "reason":"prepared_stage_promotion_failed"})
            _report_problem("Authorized stage could not be presented")
            current.clear()
            receipt.clear()
            admission_state.clear()
            renderer = null
            return
    last_activated_segment = expected
    last_activated_intent = str(receipt.get("intent_id",""))
    last_activated_attempt = int(receipt.get("attempt",-1))
    var now_ms: int = Time.get_ticks_msec()
    var deadline_local: float = float(receipt["deadline_ms"]) + \
        float(now_ms)-_backend_ms()
    if not current.is_empty() and float(current.get("count_in_beats",0.0)) > 0.0 and \
            not bool(current.get("reused_count_in",false)):
        metronome.reserve_count_in(
            deadline_local, float(current.get("bpm",60.0)),
            float(current.get("count_in_beats",0.0)),
            current.get("count_in_meter",[4,4]),
            float(current.get("count_in_beats",0.0)),
            str(current.get("action","start")))
        metronome.acknowledge_reserved_count_in(now_ms)
    renderer = null
    current.clear()
    receipt.clear()
    admission_state.clear()
    started_ms = -1

func _cancel_provisional() -> void:
    if renderer != null and is_instance_valid(renderer):
        renderer.cancel_stream_arm()
    if not current.is_empty() and withdraw_request._pending_id < 0:
        withdraw_request.request("playback.withdraw",{
            "intent_id":str(current["intent_id"]),
            "attempt":int(current["attempt"]),
            "reason":"presentation_cancelled"})
    # No provisional transaction owns an audible countdown: that
    # reservation is created only after authorization. Cancelling here
    # could otherwise silence the previous take's still-active count-in.
    renderer = null
    current.clear()
    receipt.clear()
    admission_state.clear()
    pending_reconciliation = false
    started_ms = -1

func _withdrawn(_code: int, _body: PackedByteArray) -> void:
    pass

func _failure_reported(code: int, body: PackedByteArray) -> void:
    if code != 0:
        _report_problem("Could not halt playback after notation loss: "+body.get_string_from_utf8())
