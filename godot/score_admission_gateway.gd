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
var last_rejected_fixed_intent := ""

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

func _reject_fixed_intent(intent: Dictionary, reason: String) -> void:
    # An announced automatic repeat has only one immutable deadline.
    # If that slot has expired or physically overlaps ink, waiting for
    # another frame or inventing a later slot is incorrect. Ask the
    # authoritative backend to retire that exact pending attempt.
    var key: String = str(intent.get("intent_id","")) + ":" + \
        str(intent.get("attempt",-1))
    if key == last_rejected_fixed_intent or withdraw_request.is_pending():
        return
    var payload := {
        "intent_id":str(intent.get("intent_id","")),
        "attempt":int(intent.get("attempt",-1)),
        "reason":reason,
    }
    if withdraw_request.request("playback.withdraw",payload) == OK:
        last_rejected_fixed_intent = key
        _report_problem(reason)


func _matching_renderer(intent: Dictionary):
    if score_session != null and score_session.matches_ready_source(intent):
        return stage.renderer
    return runway.prepared_renderer(intent) if runway != null else null


func _admit(intent: Dictionary, state: Dictionary, _accepted_frame_ms: int) -> void:
    var view = _matching_renderer(intent)
    if view == null or not is_instance_valid(view):
        return
    if (str(state.get("piece_fingerprint","")) != str(intent.get("fingerprint",""))
            or int(state.get("revision",-1)) != int(intent.get("revision",-2))):
        return
    var source_timing: Dictionary = state.get("practice_timeline",{})
    if (absf(view.timeline.duration_beats -
            float(source_timing.get("source_duration_beats",-1.0))) > 0.0001
            or absf(view.timeline.sounding_duration_beats -
                float(source_timing.get("sounding_duration_beats",-1.0))) > 0.0001
            or absf(float(intent.get("end_beat",-1.0)) -
                view.timeline.sounding_duration_beats) > 0.0001):
        # The prepared assets must cover the full selected PracticeWindow,
        # including a cross-bar key release. Never admit another window's
        # notes merely because its initial source beat matches.
        return
    # Capture the two physical-clock coordinates together at admission,
    # not at a possibly old state-reply timestamp. All projection queries
    # below use this exact local sample and the witness carries the
    # corresponding native/Python monotonic timestamp.
    var frame_ms: int = Time.get_ticks_msec()
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
    # Physical travel follows the *already authorized* source epochs
    # until the successor is presented. A new intent may belong to
    # another stage/BPM, and a paused active source still has its authored
    # tempo map. Never infer the map from a UI phase or future intent.
    var ledger: Variant = state.get("playback_timeline")
    var committed: Variant = ledger.get("current") if ledger is Dictionary else null
    var tempo: float = maxf(1.0,float(
        committed.get("bpm",intent.get("bpm",40.0))
        if committed is Dictionary else intent.get("bpm",40.0)))
    var authored: Array = (
        committed.get("tempo_segments",[])
        if committed is Dictionary else [])
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
    var fixed: Variant = intent.get("fixed_deadline_ms")
    if fixed != null:
        if action != "auto" or not is_finite(float(fixed)) or float(fixed) <= backend_now:
            _reject_fixed_intent(intent,
                "Direct repeat deadline expired before score admission")
            return
        var exact_world: float = flow.project_authored_future(
            frame_ms+roundi(float(fixed)-backend_now),frame_ms,
            float(state.get("clock_beat",0.0)),tempo,authored)
        planned = view.reserve_continuation_at(world,opening,exact_world,count_in)
        if planned.is_empty():
            _reject_fixed_intent(intent,
                "Cannot admit the direct repeat at its one-bar deadline")
            return
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
                    not bool(planned.get("reused_unplayed_count_in",false)):
                view.cancel_stream_arm()
                planned.clear()
    if planned.is_empty():
        # Every newly inserted source gets its own complete bar. Reuse is
        # the sole exception; the count-in is never silently shortened.
        planned = view.reserve_transport_action(
            reservation_action,world,opening,required_slot,
            str(intent.get("mode","")) == "listen")
    if planned.is_empty():
        _report_problem("Cannot reserve source notation for this playback")
        return
    # From here the gateway owns only provisional physical ink. Python
    # decides the musical deadline from this source-bound placement witness.
    renderer = view
    admission_state = state.duplicate(true)
    current = intent.duplicate(true)
    started_ms = frame_ms
    var start_world: float = float(planned.get("start_world", NAN))
    var physical_travel_ms: float = flow.physical_travel_ms_to(
        start_world,frame_ms,float(state.get("clock_beat",0.0)),
        tempo,authored)
    if not is_finite(physical_travel_ms):
        _cancel_provisional()
        return
    current["world_origin"] = start_world
    current["reused_count_in"] = bool(
        planned.get("reused_unplayed_count_in",false))
    var payload: Dictionary = {
        "intent_id": str(intent["intent_id"]),
        "attempt": int(intent["attempt"]),
        "take_id": str(intent["take_id"]),
        "fingerprint": str(intent["fingerprint"]),
        "stage_key": str(intent["stage_key"]),
        "revision": int(intent["revision"]),
        "hand": str(intent["hand"]),
        "source_from_beat": opening,
        "source_end_beat": float(intent["end_beat"]),
        "sampled_at_ms": backend_now,
        "travel_ms": physical_travel_ms,
        "world_origin": start_world,
        "queue_generation": view.admission_queue_generation(),
        "renderer_generation": int(intent["revision"]),
        "reused_count_in": bool(current["reused_count_in"]),
    }
    # This witness is immutable for the life of the provisional arm.
    # A lost reserve response is recovered from the backend ledger only
    # when all source and physical identity fields match this exact offer.
    current["physical_offer"] = payload.duplicate(true)
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
    if (not pending_segment.is_empty() and active_segment == pending_segment
            and str(timeline.get("state","")) not in ["failed","idle"]):
        # The published active timeline intentionally has no request ID
        # or attempt. The segment matched our previously verified receipt,
        # so confirm with that immutable receipt, never with the reduced
        # read model as though it were a reserve/present reply.
        pending_reconciliation = false
        _confirm_authorized(receipt)
    if timeline is Dictionary:
        var segment: String = str(timeline.get("segment_id",""))
        if bool(state.get("running", false)) and \
                str(state.get("phase", "")) == "playing" and \
                not segment.is_empty() and \
                stage.renderer != null and \
                stage.renderer.bound_segment_id() != segment:
            missing_score_frames += 1
            if missing_score_frames >= 4 and reported_failure_segment != segment:
                reported_failure_segment = segment
                if not failure_request.is_pending():
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
            if reserve_request.is_pending() or \
                    present_request.is_pending():
                return
            if not receipt.is_empty() or pending_reconciliation:
                pending_reconciliation = true
                if not status_request.is_pending() and \
                        Time.get_ticks_msec()-started_ms >= 400:
                    started_ms = Time.get_ticks_msec()
                    _query_status()
            else:
                _cancel_provisional()
        return
    var identifier: String = str(intent.get("intent_id",""))
    var attempt: int = int(intent.get("attempt",-1))
    if identifier == last_activated_intent and attempt == last_activated_attempt:
        return
    if not current.is_empty():
        if str(current.get("intent_id","")) == identifier and \
                int(current.get("attempt",-2)) == attempt:
            if pending_reconciliation and not present_request.is_pending() and \
                    not reserve_request.is_pending() and \
                    not status_request.is_pending() and \
                    Time.get_ticks_msec()-started_ms > 800:
                started_ms = Time.get_ticks_msec()
                _query_status()
            return
        # This is a NEW intent. Reconcile the former reservation before
        # touching its ink, because its result can arrive out of order.
        if reserve_request.is_pending() or \
                present_request.is_pending() or \
                status_request.is_pending():
            return
        if not receipt.is_empty() or pending_reconciliation:
            pending_reconciliation = true
            _query_status()
            return
        _cancel_provisional()
    if reserve_request.is_pending() or present_request.is_pending():
        return
    _admit(intent,state,frame_ms)

func _matches_intent(reply: Dictionary, expected: Dictionary) -> bool:
    return (str(reply.get("intent_id","")) == str(expected.get("intent_id",""))
        and int(reply.get("attempt",-1)) == int(expected.get("attempt",-2))
        and str(reply.get("take_id","")) == str(expected.get("take_id","")))

func _matches_reservation(reply: Dictionary) -> bool:
    if current.is_empty() or not _matches_intent(reply,current) or \
            not bool(reply.get("reserved",false)):
        return false
    var offer: Variant = current.get("physical_offer")
    if not offer is Dictionary:
        return false
    # A segment name or take ID alone cannot attest ownership: an earlier
    # arm for the same intent could have been withdrawn and replaced.
    # The ledger receipt must describe this exact immutable stream arm.
    return (not str(reply.get("segment_id","")).is_empty()
        and is_finite(float(reply.get("deadline_ms",NAN)))
        and float(reply.get("deadline_ms",NAN)) > 0.0
        and is_finite(float(reply.get("world_origin",NAN)))
        and absf(float(reply.get("world_origin",NAN)) -
            float(offer.get("world_origin",NAN))) <= .00001
        and int(reply.get("queue_generation",-1)) ==
            int(offer.get("queue_generation",-2))
        and int(reply.get("renderer_generation",-1)) ==
            int(offer.get("renderer_generation",-2))
        and absf(float(reply.get("sampled_at_ms",NAN)) -
            float(offer.get("sampled_at_ms",NAN))) <= .001
        and absf(float(reply.get("travel_ms",NAN)) -
            float(offer.get("travel_ms",NAN))) <= .001
        and bool(reply.get("reused_count_in",false)) ==
            bool(offer.get("reused_count_in",false)))


func _bind_backend_reservation(authorized_offer: Dictionary) -> void:
    if not _matches_reservation(authorized_offer):
        _report_problem("Backend reserved different physical score source")
        _cancel_provisional()
        return
    receipt = authorized_offer.duplicate(true)
    if renderer == null or not is_instance_valid(renderer) or \
            not renderer.bind_stream_segment(str(receipt["segment_id"])) or \
            not renderer.acknowledge_stream_arm():
        _cancel_provisional()
        return
    # A recovered reservation follows the exact same two-phase commit:
    # the prepared score is still provisional until playback.present.
    pending_reconciliation = false
    _send_presentation()


func _reserved(code: int, body: PackedByteArray) -> void:
    if current.is_empty():
        return
    var data: Variant = JSON.parse_string(body.get_string_from_utf8())
    if code == 0 and data is Dictionary and _matches_reservation(data):
        _bind_backend_reservation(data)
        return
    # The worker may have COMMITTED reserve before its reply was dropped
    # or timed out. Do not cancel that physical arm on callback status.
    # Read the backend ledger first and accept only the original witness.
    pending_reconciliation = true
    if code != 0:
        _report_problem("Score reservation reply uncertain; reconciling")
    else:
        _report_problem("Score reservation reply mismatched; checking ledger")
    _query_status()


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
            bool(data.get("authorized",false)) and \
            _matches_intent(data,receipt) and \
            str(data.get("segment_id","")) == str(receipt.get("segment_id","")):
        pending_reconciliation = false
        _confirm_authorized(data)
    else:
        # In-process timeouts can lose a response after the backend already
        # committed the transport. Query its transaction ledger first.
        pending_reconciliation = true
        _query_status()

func _query_status() -> void:
    if not status_request.is_pending() and not current.is_empty():
        status_request.request("playback.status")

func _status_received(code: int, body: PackedByteArray) -> void:
    if not pending_reconciliation or current.is_empty():
        return
    if code != 0:
        # No rollback on an uncertain status response; polling the active
        # transaction will retry after the bounded interval.
        return
    var status: Variant = JSON.parse_string(body.get_string_from_utf8())
    if not status is Dictionary:
        return
    var ledger_offer: Variant = status.get("reservation")
    if receipt.is_empty():
        if (ledger_offer is Dictionary and
                _matches_reservation(ledger_offer) and
                str(status.get("state","")) == "reserved"):
            # The reserve reply was lost after commit. The backend ledger
            # provides the same immutable receipt; bind and present once.
            _bind_backend_reservation(ledger_offer)
            return
        # With no local receipt, we have not sent playback.present.
        # The backend therefore cannot have authorized THIS tentative
        # arm. A different/absent ledger reservation means rollback.
        _cancel_provisional()
        return
    var expected: String = str(receipt.get("segment_id",""))
    if (str(status.get("active_segment_id","")) == expected and
            str(status.get("active_take_id","")) ==
                str(receipt.get("take_id","")) and
            str(status.get("state","")) not in ["failed","idle"]):
        _confirm_authorized(receipt)
        return
    if (ledger_offer is Dictionary and
            _matches_reservation(ledger_offer) and
            str(status.get("reserved_segment_id","")) == expected and
            str(status.get("state","")) == "reserved"):
        pending_reconciliation = false
        _send_presentation()
        return
    # The backend has no matching active or reserved segment.
    # Withdraw only the local provisional ink, never the prior live take.
    _cancel_provisional()


func _confirm_authorized(data: Dictionary) -> void:
    if receipt.is_empty():
        return
    var expected: String = str(receipt.get("segment_id",""))
    if str(data.get("segment_id","")) != expected or \
            not _matches_intent(data,receipt):
        pending_reconciliation = true
        _query_status()
        return
    if (renderer == null or not is_instance_valid(renderer)
            or not renderer.owns_authorized_segment(expected)):
        # The backend may already be grading this exact take, but native
        # physical source ownership was lost across a resize/withdrawal.
        # Stop that take instead of starting count-in sound over blank ink.
        if not failure_request.is_pending():
            failure_request.request("playback.failure",{
                "take_id":str(receipt.get("take_id","")),
                "segment_id":expected,
                "reason":"authorized_source_missing_from_physical_queue"})
        _report_problem("Authorized score source disappeared before presentation")
        if renderer != null and is_instance_valid(renderer):
            renderer.cancel_stream_arm()
        current.clear()
        receipt.clear()
        admission_state.clear()
        renderer = null
        started_ms = -1
        pending_reconciliation = false
        return
    if runway != null and renderer != null and \
            is_instance_valid(renderer) and runway.owns_prepared_renderer(renderer):
        if not runway.promote_reserved(admission_state):
            if not failure_request.is_pending():
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
    if not current.is_empty():
        # Admission authorizes the exact source rate epochs before their
        # scheduled downbeat. Renderer, inverse physical preflight and
        # count-in now consume this same deterministic presentation clock.
        flow.authorize_source_epoch(
            deadline_local,float(current.get("from_beat",0.0)),
            float(current.get("bpm",60.0)),
            current.get("tempo_segments",[]),expected)
    if not current.is_empty() and float(current.get("count_in_beats",0.0)) > 0.0 and \
            not bool(current.get("reused_count_in",false)):
        metronome.reserve_count_in(
            deadline_local, float(current.get("bpm",60.0)),
            float(current.get("count_in_beats",0.0)),
            current.get("count_in_meter",[4,4]),
            float(current.get("count_in_beats",0.0)),
            str(current.get("action","start")),
            current.get("count_in_plan",{}),
            str(receipt.get("take_id","")))
        metronome.acknowledge_reserved_count_in(now_ms)
    renderer = null
    current.clear()
    receipt.clear()
    admission_state.clear()
    started_ms = -1

func _cancel_provisional() -> void:
    if renderer != null and is_instance_valid(renderer):
        renderer.cancel_stream_arm()
    if not current.is_empty() and not withdraw_request.is_pending():
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

func _withdrawn(code: int, body: PackedByteArray) -> void:
    # The backend may already have expired/superseded this attempt.
    # No local retry creates a second deadline: the next authoritative
    # state snapshot decides whether another attempt exists.
    if code != 0:
        _report_problem("Could not retire score reservation: " +
            Request.failure_message(code,body))

func _failure_reported(code: int, body: PackedByteArray) -> void:
    if code != 0:
        _report_problem("Could not halt playback after notation loss: "+body.get_string_from_utf8())
