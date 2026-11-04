extends Node
## Prepare the exact next Coda/Fukuda score while the current one scrolls.
## Only a fully retained and engine-acknowledged score can be promoted. Manual
## navigation and unsuccessful attempts preserve their existing behavior.
const Request := preload("res://inprocess_request.gd")
const NativeView := preload("res://notation/native/view.gd")
const NativeAssets := preload("res://native_score_assets.gd")
const MAX_PRELOAD_FAILURES := 3
signal renderer_promoted(new_renderer)
signal preload_problem(message: String)

var stage
var score_session
var _fetch: Node
var _ack: Node
var _report: Node
var _future
# Last lesson's authentic ink remains visible behind the playhead until its
# final bar has left the viewport; no score-page flash at promotion.
var _tail
var _tail_origin := 0.0
var _tail_end := 0.0
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
    _clear_tail()
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
    _native_failures = 0
    _terminal_preload_failure = false
    _report_accepted = false

func _clear_tail() -> void:
    if _tail != null and is_instance_valid(_tail):
        _tail.queue_free()
    _tail = null
    _tail_origin = 0.0
    _tail_end = 0.0

func _advance_tail(global_beat: float) -> void:
    if _tail == null:
        return
    if not is_instance_valid(_tail):
        _tail = null
        return
    _tail.present_clock(global_beat-_tail_origin,global_beat-_tail_origin)
    var density: float = maxf(1.0,float(_tail.timeline.pixels_per_beat))
    var left_visible: float = global_beat-_tail.size.x*.42/density
    if left_visible > _tail_end+.01:
        _clear_tail()

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
    # Preserve the active learner's horizontal density setting across
    # precompiled stages; retain native collision fitting if it needs more.
    if is_instance_valid(stage.renderer):
        _future.set_density(float(stage.renderer.configured_density))
    _future.runway_overlay = true
    _future.set_transport_overlay_enabled(false)
    _future.mouse_filter = Control.MOUSE_FILTER_IGNORE
    stage.score_frame.add_child(_future)
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

func present_frame(state: Dictionary, global_beat: float) -> void:
    _visual_beat = global_beat
    _advance_tail(global_beat)
    if _future == null or not is_instance_valid(_future) or _bundle.is_empty():
        if stage != null and stage.renderer != null and is_instance_valid(stage.renderer):
            var last_clean: bool = \
                str(state.get("mode","")) == "practice" and \
                int(state.get("lesson_step",0)) < int(state.get("lesson_steps",0)) and \
                int(state.get("streak",0)) >= int(state.get("clean_runs_required",3)) - 1 and \
                float(state.get("bpm",0)) >= float(state.get("target_bpm",INF)) and \
                str(state.get("phase","")) in ["playing","count_in","feedback","preview_gap"]
            if last_clean:
                var current_end: float = (float(state.get("visual_offset_beats",0.0)) +
                    float(state.get("duration_beats",0.0)) +
                    .20 * float(state.get("bpm",60.0)) / 60.0)
                # Suppress stale repeating notes where the next real score is
                # still missing. The old ink keeps moving offscreen naturally.
                stage.renderer.runway_cutoff_beat = current_end - \
                    float(stage.renderer.runway_origin_beat)
            else:
                stage.renderer.runway_cutoff_beat = INF
            if stage.has_method("present_runway_steps"):
                stage.present_runway_steps(state,global_beat)
        return
    var stride: float = float(state.get("practice_timeline",{}).get("stride_beats",0.0))
    if stride <= 0.0:
        return
    # A delayed, exact-score handoff extends the empty scrolling runway.
    # The backend publishes the same global beat it adopts as the new
    # renderer's origin; no second clock or reset is introduced here.
    var natural_start: float = (float(state.get("visual_offset_beats",0.0)) +
        float(state.get("duration_beats",0.0)) +
        .20 * float(state.get("bpm",60.0)) / 60.0)
    var next_start: float = float(state.get("next_stage_start_beat", natural_start))
    var local_beat: float = global_beat - next_start
    _future.present_clock(local_beat,local_beat)
    if _future.retained_ready() and not _acknowledged and not _ack_waiting \
            and not _terminal_preload_failure and \
            Time.get_ticks_msec() >= _next_poll_ms:
        _ack_waiting = _ack.request("score.stage_ready",{
            "stage_key":_bundle["stage_key"],
            "revision":_bundle["revision"]}) == OK
    var last_clean: bool = int(state.get("streak",0)) >= \
            int(state.get("clean_runs_required",3)) - 1 and \
            float(state.get("bpm",0)) >= float(state.get("target_bpm",INF))
    var active_phase: bool = str(state.get("phase","")) in \
        ["playing","count_in","feedback","preview_gap"]
    var display: bool = _acknowledged and last_clean and active_phase
    _future.modulate.a = 1.0 if display else 0.001
    if is_instance_valid(stage.renderer):
        # Partially compiled but unacknowledged future ink must not expose
        # stale repeating current-stage notes. Keep its natural endpoint
        # clipped until the complete next renderer can be shown.
        var end_beat: float = next_start if display else \
            (natural_start if last_clean and active_phase else INF)
        stage.renderer.runway_cutoff_beat = end_beat - \
            float(stage.renderer.runway_origin_beat) if is_finite(end_beat) else INF
    if stage.has_method("present_runway_steps"):
        stage.present_runway_steps(state,global_beat,
            next_start if _acknowledged else INF,
            str(_bundle.get("stage_label",_bundle.get("level","Next step"))))

func promote_if_ready(state: Dictionary) -> bool:
    if _future == null or not is_instance_valid(_future) or \
            not _acknowledged or not _future.retained_ready():
        return false
    if str(state.get("piece_fingerprint","")) != _source_fingerprint or \
            int(state.get("revision",-1)) != int(_bundle.get("revision",-2)) or \
            int(state.get("lesson_step",0)) != int(_bundle.get("step_number",-1)):
        return false
    var old = stage.renderer
    var former_origin: float = float(old.runway_origin_beat)
    var new_renderer = _future
    _future = null
    new_renderer.modulate.a = 1.0
    new_renderer.runway_overlay = false
    # Retained note ink is unchanged; its fixed brace and annotation canvas
    # was intentionally omitted while this was a transparent future layer.
    # Repaint that one small layer at promotion, never all score segments.
    if is_instance_valid(new_renderer.retained_annotations):
        new_renderer.retained_annotations.queue_redraw()
    new_renderer.runway_origin_beat = float(state.get("visual_offset_beats",0.0))
    new_renderer.runway_cutoff_beat = INF
    new_renderer.set_transport_overlay_enabled(true)
    stage.renderer = new_renderer
    score_session.adopt_prepared(state,new_renderer,_layout)
    renderer_promoted.emit(new_renderer)
    if old != null and is_instance_valid(old):
        _clear_tail()
        old.runway_overlay = true
        if is_instance_valid(old.retained_annotations):
            old.retained_annotations.queue_redraw()
        old.runway_cutoff_beat = (float(state.get("visual_offset_beats",0.0)) -
            former_origin)
        old.set_transport_overlay_enabled(false)
        old.mouse_filter = Control.MOUSE_FILTER_IGNORE
        old.queue_redraw()
        stage.score_frame.move_child(old,stage.score_frame.get_child_count()-1)
        _tail = old
        _tail_origin = former_origin
        _tail_end = float(state.get("visual_offset_beats",0.0))
    _bundle.clear()
    _layout.clear()
    _acknowledged = false
    _native_failures = 0
    _terminal_preload_failure = false
    _report_accepted = false
    _source_revision = int(state.get("revision",-1))
    _source_step = int(state.get("lesson_step",0))
    _source_fingerprint = str(state.get("piece_fingerprint",""))
    _next_poll_ms = Time.get_ticks_msec() + 500
    return true
