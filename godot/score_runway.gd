extends Node
## Prepare the exact next Coda/Fukuda score while the current one scrolls.
## Only a fully retained and engine-acknowledged score can be promoted. Manual
## navigation and unsuccessful attempts preserve their existing behavior.
const Request := preload("res://inprocess_request.gd")
const NativeView := preload("res://notation/native/view.gd")
const NativeAssets := preload("res://native_score_assets.gd")
const StepTimeline := preload("res://score_step_timeline.gd")
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

func _retain_tail(old, keep_staff: bool = false) -> void:
    if old == null or not is_instance_valid(old) or _tails.has(old):
        # Each outgoing renderer is registered exactly once. Duplicate
        # handoff notifications cannot scroll/retire its notes twice.
        return
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
    # A previous step may still have visible noteheads while the NEXT
    # step is itself handed off. Keep all outgoing layers on the same axis.
    for index in range(_tails.size()-1,-1,-1):
        var tail = _tails[index]
        if tail == null or not is_instance_valid(tail):
            _tails.remove_at(index)
            continue
        tail.present_flow(global_beat,{},0.0,false)
        if tail.stream_passes.is_empty() and tail != _manual_staff_tail:
            tail.queue_free()
            _tails.remove_at(index)


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
    stage.score_frame.add_child(incoming)
    stage.score_frame.move_child(incoming,outgoing.get_index()+1)
    incoming.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    incoming.visible = false
    stage.renderer = incoming
    score_session.replace_renderer(incoming)
    renderer_promoted.emit(incoming)
    if outgoing.stream_passes.is_empty():
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
        var lead: float = maxf(5.0,
            _future._stream_right_beats()+
            _future._stream_header_beats(0.0)+1.5)
        _ack_waiting = _ack.request("score.stage_ready",{
            "stage_key":_bundle["stage_key"],
            "revision":_bundle["revision"],
            "presentation_lead_beats":lead}) == OK


func promote_if_ready(state: Dictionary) -> bool:
    if _future == null or not is_instance_valid(_future) or \
            not _acknowledged or not _future.retained_ready():
        return false
    if str(state.get("piece_fingerprint","")) != _source_fingerprint or \
            int(state.get("revision",-1)) != int(_bundle.get("revision",-2)) or \
            int(state.get("lesson_step",0)) != int(_bundle.get("step_number",-1)):
        return false
    var old = stage.renderer
    var new_renderer = _future
    # The new source can enter ONLY at the backend's already-scheduled
    # future downbeat. Do not promote a renderer with missing/late timing,
    # and never calculate a replacement onset in the current frame.
    var graded: float = float(state.get("clock_beat",-INF))
    if not is_finite(graded) or graded >= 0.0:
        return false
    var intended_world: float = _visual_beat - graded
    var armed: Dictionary = new_renderer.arm_stream_take(
        _visual_beat,0.0,intended_world)
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
