extends Node
## Prepare the exact next Coda/Fukuda score while the current one scrolls.
## Only a fully retained and engine-acknowledged score can be promoted. Manual
## navigation and unsuccessful attempts preserve their existing behavior.
const Request := preload("res://inprocess_request.gd")
const NativeView := preload("res://notation/native/view.gd")
const NativeAssets := preload("res://native_score_assets.gd")
const StepTimeline := preload("res://score_step_timeline.gd")
const StreamAdmission := preload("res://score_stream_admission.gd")
const StreamQueue := preload("res://score_stream_queue.gd")
const MAX_PRELOAD_FAILURES := 3
signal renderer_promoted(new_renderer)
signal preload_problem(message: String)

var stage
var score_session
var _fetch: Node
var _ack: Node
var _report: Node
var _future
# Every outgoing score owns its retained ink until its last clip leaves.
# Two quick lesson changes may overlap: there is no single-tail shortcut.
var _tails: Array = []
# During an unprepared manual revision, this outgoing renderer temporarily
# owns the visible staff and playhead until replacement ink is published.
var _manual_staff_tail
var _bundle: Dictionary = {}
var _layout: Dictionary = {}
var _source_fingerprint := ""
var _source_revision := -1
var _source_step := -1
var _next_poll_ms := 0
var _acknowledged := false
var _ack_waiting := false
var _failure := ""
var _reported_failure := ""
var _native_failures := 0
var _terminal_preload_failure := false
var _report_accepted := false
var _visual_beat := 0.0
var _future_intro_offset := 0.0

func configure(host: Node, practice_stage, session, bus: Node) -> void:
    stage = practice_stage
    score_session = session
    _fetch = Request.new()
    _fetch.timeout = 90.0
    host.add_child(_fetch)
    _fetch.configure(bus)
    _fetch.request_completed.connect(_on_future_reply)
    _ack = Request.new()
    _ack.timeout = 15.0
    host.add_child(_ack)
    _ack.configure(bus)
    _ack.request_completed.connect(_on_ack_reply)
    _report = Request.new()
    _report.timeout = 15.0
    host.add_child(_report)
    _report.configure(bus)
    _report.request_completed.connect(_on_report_reply)

func _discard() -> void:
    if stage != null and stage.renderer != null and is_instance_valid(stage.renderer):
        stage.renderer.runway_cutoff_beat = INF
    # Preload invalidation never retires music already moving offscreen.
    _fetch.cancel_request()
    _ack.cancel_request()
    _report.cancel_request()
    if _future != null and is_instance_valid(_future):
        # A preloader contains only an unadmitted, reconstructible asset.
        # Musical source plans are retained by the authoritative journal,
        # never copied into a second in-memory ScoreRunway history.
        _future.queue_free()
    _future = null
    _bundle.clear()
    _layout.clear()
    _acknowledged = false
    _ack_waiting = false
    _next_poll_ms = 0
    _failure = ""
    _reported_failure = ""
    _future_intro_offset = 0.0
    _native_failures = 0
    _terminal_preload_failure = false
    _report_accepted = false

func _link_existing_layers(incoming) -> void:
    # All renderer layers live on one visual world axis. Queue ownership
    # stays with the originating renderer; every new admission must check
    # the previously committed ink in ALL still-live predecessor layers.
    if not incoming is NativeView:
        return
    var predecessors: Array = _tails.duplicate()
    if stage != null and stage.renderer != null:
        predecessors.append(stage.renderer)
    for previous in predecessors:
        if previous != incoming and previous is NativeView and \
                is_instance_valid(previous):
            incoming._stream_queue.register_peer(previous)


func _retain_tail(old, keep_staff: bool = false) -> void:
    if old == null or not is_instance_valid(old) or _tails.has(old):
        return
    # Lesson changes retract the maximal never-seen future suffix before
    # handing off the old renderer. Already-visible notes remain immutable.
    old.trim_future_queue("lesson_handoff")
    old.runway_overlay = not keep_staff
    if is_instance_valid(old.retained_annotations):
        old.retained_annotations.queue_redraw()
    old.runway_cutoff_beat = INF
    old.set_transport_overlay_enabled(keep_staff)
    old.mouse_filter = Control.MOUSE_FILTER_IGNORE
    old.queue_redraw()
    # Leave outgoing ink below the fixed HUD. Moving a tail to the end of
    # score_frame makes it paint over the count-in and note feedback.
    if stage.renderer != old and old.get_parent() == stage.score_frame and \
            is_instance_valid(stage.renderer) and \
            old.get_index() > stage.renderer.get_index():
        stage.score_frame.move_child(old,stage.renderer.get_index())
    _tails.append(old)
    if keep_staff:
        _manual_staff_tail = old


func active_revision_published(_revision: int) -> void:
    # Called by ScoreAssetSession only once the replacement has completed
    # authentic engraving. This is the handoff of staff/cursor ownership.
    if _manual_staff_tail == null:
        return
    if is_instance_valid(_manual_staff_tail):
        _manual_staff_tail.runway_overlay = true
        _manual_staff_tail.set_transport_overlay_enabled(false)
        _manual_staff_tail.queue_redraw()
    _manual_staff_tail = null


func _advance_tails(global_beat: float) -> void:
    # The renderer layers are ONE ordered FIFO of successive score sources.
    # Every layer projects on the same global clock; a later renderer can
    # never be freed ahead of an older layer still displaying notation.
    for tail in _tails:
        if tail != null and is_instance_valid(tail):
            tail.present_flow(global_beat,{},0.0,false)
    while not _tails.is_empty():
        var first = _tails[0]
        if first == null or not is_instance_valid(first):
            _tails.pop_front()
            continue
        if first == _manual_staff_tail or first.stream_pass_count() > 0:
            break
        # The source queue has already journaled all withdrawn/expired ink.
        first.queue_free()
        _tails.pop_front()


func _on_future_reply(code: int, body: PackedByteArray) -> void:
    if code != 0:
        _register_preload_failure(
            "Next lesson preloading request failed (status %d)" % code)
        return
    var value: Variant = JSON.parse_string(body.get_string_from_utf8())
    if not value is Dictionary:
        _register_preload_failure("Invalid future score response")
        return
    if str(value.get("status","")) == "preparing":
        _next_poll_ms = Time.get_ticks_msec() + 600
        return
    if str(value.get("status","")) == "none":
        _next_poll_ms = Time.get_ticks_msec() + 3000
        return
    if str(value.get("status","")) != "ready":
        _failure = str(value.get("error","Next score cannot be engraved"))
        if str(value.get("status","")) == "error":
            _terminal_preload_failure = true
            _report_accepted = true # The Python preloader already owns this error.
            if _failure != _reported_failure:
                _reported_failure = _failure
                preload_problem.emit("Next lesson score failed: " + _failure)
        else:
            _register_preload_failure(_failure)
        return
    if int(value.get("revision",-1)) != _source_revision + 1 or \
            int(value.get("step_number",-1)) != _source_step + 1 or \
            str(value.get("fingerprint","")) != _source_fingerprint:
        return
    var layout_data: Variant = value.get("layout")
    var model_data: Variant = value.get("model")
    if not layout_data is Dictionary or not model_data is Dictionary:
        _register_preload_failure(
            "Future score lacks authentic layout or semantic model")
        return
    _future = NativeView.new()
    # A future stage must use the same staff presentation and background
    # as the active stage before its retained note ink is pre-engraved.
    if is_instance_valid(stage.renderer):
        _future.external_backdrop = stage.renderer.external_backdrop
        _future.compact_inactive_staff = stage.renderer.compact_inactive_staff
        # Use the NEXT stage's published hand, not the current stage's hand.
        # Pre-engraving must already occupy the eventual single-staff lane.
        _future.active_hand = str(value.get("hand","both"))
    # Preserve the active learner's horizontal density setting across
    # precompiled stages; retain native collision fitting if it needs more.
    if is_instance_valid(stage.renderer):
        _future.set_density(float(stage.renderer.configured_density))
    _future.runway_overlay = true
    _future.set_transport_overlay_enabled(false)
    _future.mouse_filter = Control.MOUSE_FILTER_IGNORE
    stage.score_frame.add_child(_future)
    # Retained score layers belong at the original notation z-order,
    # underneath count-in, note feedback and practice controls.
    stage.score_frame.move_child(_future,stage.renderer.get_index()+1)
    _future.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    _future.modulate.a = 0.001
    _future.visible = true
    var installed: Dictionary = NativeAssets.install(_future,layout_data)
    if not bool(installed.get("ok",false)) or not _future.load_score(model_data):
        var message: String = str(installed.get("error",_future.failure_reason))
        _future.queue_free()
        _future = null
        _register_preload_failure(message)
        return
    _bundle = value
    _layout = installed["layout"]
    _future_intro_offset = StepTimeline.first_playable_beat(
        model_data,str(value.get("hand","both")))
    _native_failures = 0
    _failure = ""
    # The future stage's own notes and active hand are positioned on a
    # local score axis; Main feeds it the global minus next-stage origin.
    _future.present({
        "running":true,"paused":false,"phase":"playing",
        "score_loop_enabled":false,"play_from_beat":0.0,
        "hand":str(value.get("hand","both")),
        "practice_preparation":null},-50.0,-50.0)
    _next_poll_ms = 0

func _on_ack_reply(code: int, body: PackedByteArray) -> void:
    _ack_waiting = false
    var value: Variant = JSON.parse_string(body.get_string_from_utf8())
    _acknowledged = code == 0 and value is Dictionary and \
            bool(value.get("accepted",false))
    if not _acknowledged:
        _register_preload_failure("Future score acknowledgement rejected")

func _register_preload_failure(message: String) -> void:
    _failure = message if not message.is_empty() else "Native next-step notation failed"
    _native_failures += 1
    var backoff_ms: int = 500 * (1 << mini(_native_failures - 1, 4))
    _next_poll_ms = Time.get_ticks_msec() + backoff_ms
    if _native_failures >= MAX_PRELOAD_FAILURES:
        _terminal_preload_failure = true
        if _failure != _reported_failure:
            _reported_failure = _failure
            preload_problem.emit("Next lesson score failed: " + _failure)
        _report_if_needed(Time.get_ticks_msec())

func _report_if_needed(now_ms: int) -> void:
    if not _terminal_preload_failure or _report_accepted or \
            _report._pending_id >= 0 or now_ms < _next_poll_ms:
        return
    if _report.request("score.stage_failed",{
            "fingerprint":_source_fingerprint,
            "step_number":_source_step+1,
            "revision":_source_revision+1,
            "error":_failure}) != OK:
        _next_poll_ms = now_ms + 1000

func _on_report_reply(code: int, body: PackedByteArray) -> void:
    var value: Variant = JSON.parse_string(body.get_string_from_utf8())
    # A valid rejection means the engine has already moved to a different
    # source. That old failed score must not be reported repeatedly.
    _report_accepted = code == 0 and value is Dictionary and \
        value.has("accepted")
    if not _report_accepted:
        _next_poll_ms = Time.get_ticks_msec() + 1000

func _request_if_needed(state: Dictionary, now_ms: int) -> void:
    if _terminal_preload_failure:
        _report_if_needed(now_ms)
        return
    if _future != null or _ack_waiting or now_ms < _next_poll_ms or \
            _fetch._pending_id >= 0:
        return
    if str(state.get("mode","")) != "practice" or \
            not score_session.is_ready() or \
            int(state.get("lesson_step",0)) >= int(state.get("lesson_steps",0)):
        return
    if _fetch.request("score.next_stage") != OK:
        _next_poll_ms = now_ms + 1000

func preserve_unprepared_revision(state: Dictionary) -> bool:
    # Manual stage navigation, score reopening and other non-preloaded
    # revisions still use the same forward-only stream. Swap the asset
    # destination BEFORE ScoreAssetSession.update_context() resets it.
    # Otherwise reset_assets() clears still-visible outgoing noteheads.
    if not bool(state.get("loaded",false)) or stage == null or \
            not score_session.is_ready() or not is_instance_valid(stage.renderer):
        return false
    var next_revision: int = int(state.get("revision",-1))
    var next_fingerprint: String = str(state.get("piece_fingerprint",""))
    if next_revision == score_session.revision and \
            next_fingerprint == score_session._fingerprint:
        return false
    var outgoing = stage.renderer
    var incoming = NativeView.new()
    incoming.external_backdrop = outgoing.external_backdrop
    incoming.compact_inactive_staff = outgoing.compact_inactive_staff
    incoming.active_hand = str(state.get("hand","both"))
    incoming.set_density(float(outgoing.configured_density))
    incoming.set_transport_overlay_enabled(true)
    _link_existing_layers(incoming)
    stage.score_frame.add_child(incoming)
    stage.score_frame.move_child(incoming,outgoing.get_index()+1)
    incoming.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    incoming.visible = false
    stage.renderer = incoming
    score_session.replace_renderer(incoming)
    renderer_promoted.emit(incoming)
    if outgoing.stream_pass_count() == 0:
        outgoing.queue_free()
    else:
        _retain_tail(outgoing,true)
    return true


func update_state(state: Dictionary, now_ms: int) -> void:
    var fingerprint: String = str(state.get("piece_fingerprint",""))
    var revision: int = int(state.get("revision",-1))
    var step: int = int(state.get("lesson_step",0))
    if fingerprint != _source_fingerprint or revision != _source_revision or \
            step != _source_step:
        _discard()
        _source_fingerprint = fingerprint
        _source_revision = revision
        _source_step = step
    if not bool(state.get("loaded",false)):
        return
    _request_if_needed(state,now_ms)

func present_frame(_state: Dictionary, global_beat: float) -> void:
    _visual_beat = global_beat
    _advance_tails(global_beat)
    # A future source is pre-ENGRAVED, but no source-local animation, ghost
    # score, or second camera is permitted. Its source clip is positioned
    # beyond the right edge once the engine authorizes promotion.
    if _future == null or not is_instance_valid(_future):
        return
    _future.modulate.a = .001
    if _future.retained_ready() and not _acknowledged and not _ack_waiting and \
            not _terminal_preload_failure and \
            Time.get_ticks_msec() >= _next_poll_ms:
        # Reserve an additional 1.5 source beats for polling/IPC jitter,
        # beyond the entire offscreen staff and Verovio header. Neither
        # the frontend nor the backend may recenter a late source.
        # P5 short handoff: the engine settles the step once the outgoing
        # take's last pixel has passed (clear, beats after that take's end)
        # and opens the new stage on the empty strip one count-in bar ahead,
        # never closer than the rest gap and header (lead).
        var short: Dictionary = _short_handoff()
        var request: Dictionary = {"stage_key":_bundle["stage_key"],
            "revision":_bundle["revision"],
            "presentation_lead_beats":float(short.get("lead",maxf(5.0,
                _future._stream_right_beats()+
                _future._stream_header_beats(0.0)+1.5)))}
        if short.has("clear"):
            request["presentation_clear_beats"] = float(short["clear"])
        # The incoming stage's own short-rest geometry (its density/header)
        # times that stage's repeats once the handoff commits.
        if _future.has_method("short_rest_geometry"):
            request.merge(_future.short_rest_geometry(),true)
        _ack_waiting = _ack.request("score.stage_ready",request) == OK


func _short_handoff() -> Dictionary:
    # Geometry for opening the next stage on the empty strip (owner P5),
    # from the SAME pop-in peer rule the queue enforces
    # (ScoreStreamQueue.peer_popin_after): clear = beats after the outgoing
    # take's end until its final barline margin has passed the playhead and
    # the new density may open without ever overlapping it; lead = the rest
    # gap plus the new opening header (the engine adds one count-in bar).
    var old = stage.renderer if stage != null else null
    if old == null or not is_instance_valid(old) or old == _future or \
            old.get("timeline") == null or not old.has_method("staff_gap"):
        return {}
    var old_density: float = maxf(1.0,float(old.timeline.pixels_per_beat))
    var duration: float = float(old.timeline.duration_beats)
    var trailing: float = StreamAdmission.engraved_clip_bounds(
        0.0,duration,old_density,float(old.staff_gap()),duration).y/old_density-duration
    var density: float = maxf(1.0,float(_future.timeline.pixels_per_beat))
    var playhead: float = _future.size.x*NativeView.PLAYHEAD_FRACTION
    var rest: float = float(old.practice_timeline.get("gap",{}).get(
        "duration_beats",0.0)) if "practice_timeline" in old else 0.0
    # Round 4: the outgoing take keeps its written rest bar (one full
    # measure). The step settles at once (clear 0) and the new stage opens
    # straight after that rest bar by the pop-in rule (lead counted from
    # the take end).
    return {"clear":0.0,"lead":StreamQueue.peer_popin_after(
        maxf(rest,trailing),old_density,playhead,density)+
        _future._stream_header_beats(0.0)+
        StreamAdmission.OFFSCREEN_MARGIN_BEATS}


func promote_if_ready(state: Dictionary, run_at_world: float = NAN) -> bool:
    if _future == null or not is_instance_valid(_future) or \
            not _acknowledged or not _future.retained_ready():
        return false
    if str(state.get("piece_fingerprint","")) != _source_fingerprint or \
            int(state.get("revision",-1)) != int(_bundle.get("revision",-2)) or \
            int(state.get("lesson_step",0)) != int(_bundle.get("step_number",-1)):
        return false
    var old = stage.renderer
    var new_renderer = _future
    _link_existing_layers(new_renderer)
    # The new source can enter ONLY at the backend's already-scheduled
    # future downbeat. Do not promote a renderer with missing/late timing,
    # and never calculate a replacement onset in the current frame.
    var graded: float = float(state.get("clock_beat",-INF))
    if not is_finite(graded) or graded >= 0.0:
        return false
    # The engine's run_at projected on the presentation axis (main.gd, with
    # this snapshot's tempo already applied); the frame's cached world minus
    # the sampled clock beat is only a fallback.
    var intended_world: float = run_at_world if is_finite(run_at_world) \
        else _visual_beat - graded
    # The step opens on the empty strip one count-in bar ahead (P5).
    var armed: Dictionary = new_renderer.arm_stream_take(
        _visual_beat,0.0,intended_world,false,false,
        float(state.get("count_in_beats",0.0)))
    if armed.is_empty():
        return false
    # The future stage has already been explicitly acknowledged by the
    # backend (score.stage_ready), before its graded state appeared.
    # No second HTTP/control request exists for this promotion.
    new_renderer.acknowledge_stream_arm()
    _future = null
    new_renderer.modulate.a = 1.0
    new_renderer.runway_overlay = false
    # The same retained source ink survives this promotion. Only the
    # annotation overlay and ownership change; no camera transform resets.
    if is_instance_valid(new_renderer.retained_annotations):
        new_renderer.retained_annotations.queue_redraw()
    new_renderer.runway_origin_beat = 0.0
    new_renderer.runway_cutoff_beat = INF
    new_renderer.set_transport_overlay_enabled(true)
    new_renderer.mouse_filter = Control.MOUSE_FILTER_PASS
    if old != null and is_instance_valid(old) and \
            old.get_parent() == stage.score_frame:
        stage.score_frame.move_child(new_renderer,old.get_index()+1)
    stage.renderer = new_renderer
    score_session.adopt_prepared(state,new_renderer,_layout)
    renderer_promoted.emit(new_renderer)
    if old != null and is_instance_valid(old):
        _retain_tail(old)
    _bundle.clear()
    _layout.clear()
    _future_intro_offset = 0.0
    _acknowledged = false
    _native_failures = 0
    _terminal_preload_failure = false
    _report_accepted = false
    _source_revision = int(state.get("revision",-1))
    _source_step = int(state.get("lesson_step",0))
    _source_fingerprint = str(state.get("piece_fingerprint",""))
    _next_poll_ms = Time.get_ticks_msec() + 500
    return true
