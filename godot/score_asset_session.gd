extends RefCounted
## Owns one revision's native layout/atlas/model in-process request lifecycle.
## Borrows renderer and feedback components but no application root, widgets
## or transport resources. An obsolete worker response never publishes data.
signal request_requested(kind: String, request_id: int, path: String, timeout_seconds: float)
signal assets_invalidated(revision: int)
signal layout_published(revision: int, values: Dictionary)
signal score_published(revision: int)
signal score_failed(message: String)
signal status_changed(values: Dictionary)
signal action_requested(command: Dictionary)

const RETAINED_INK_TIMEOUT_MS := 45000
const SLOW_PREPARATION_MS := 10000
const NativeScoreAssets := preload("res://native_score_assets.gd")
const ASSET_KEYS := ["native_glyphs","native_note_templates","native_tie_templates",
    "native_chord_templates","native_beam_fragments","native_tuplet_fragments",
    "native_slur_fragments","native_required_slur_pairs","native_slurs_complete",
    "native_required_beam_groups","native_beams_complete"]

var revision := -1
var layout_revision := -1
var requested_layout_revision := -1
var timeline_model_revision := -1
var rendered_revision := -1
var native_score_piece_fingerprint := ""
var score_error := ""
var layout_pending: bool:
    get: return _requests.has("bundle")
var timeline_model_pending: bool:
    get: return layout_pending
var score_layout: Dictionary:
    get: return layout_snapshot()

var _renderer
var _feedback
var _loaded := false
var _fingerprint := ""
var _state: Dictionary = {}
var _layout: Dictionary = {}
var _generation := 0
# Retry is a genuine replay of the same source/layout request. If a
# deterministic native failure repeats unchanged, surface that fact and
# keep Browse visible rather than presenting an identical mysterious Retry.
var _last_native_failure := ""
var _retry_attempted := false
var _identical_failure_repeats := 0
var _retained_started_ms := -1
var _published_retained_generation := -1
var _preparing_since_ms := -1
var _next_request_id := 0
# One source-bound request owns the layout and original MIDI-note model.
var _requests: Dictionary = {}

func _init(renderer, native_feedback = null) -> void:
    _renderer = renderer
    _feedback = native_feedback
    if is_instance_valid(renderer) and renderer.has_signal("retained_ink_compiled"):
        renderer.connect("retained_ink_compiled",_finish_native_score)

func replace_renderer(next_renderer) -> void:
    # A manual lesson revision uses a fresh notation owner. The previous
    # retained renderer must remain alive as a moving runway tail; never
    # clear its CanvasItems through the new revision's asset lifecycle.
    if _renderer == next_renderer:
        return
    if is_instance_valid(_renderer) and \
            _renderer.has_signal("retained_ink_compiled") and \
            _renderer.is_connected("retained_ink_compiled",_finish_native_score):
        _renderer.disconnect("retained_ink_compiled",_finish_native_score)
    _renderer = next_renderer
    if is_instance_valid(next_renderer) and \
            next_renderer.has_signal("retained_ink_compiled") and \
            not next_renderer.is_connected("retained_ink_compiled",_finish_native_score):
        next_renderer.connect("retained_ink_compiled",_finish_native_score)


func source_fingerprint() -> String:
    return _fingerprint

func fingering_correction_request(source_id: String, finger: Variant,
        current_state: Dictionary, command_pending: bool) -> Dictionary:
    ## Sole identity-based admission policy for persisted fingering edits.
    ## A renderer correction cannot target a newer stage/piece or an
    ## incomplete native layout, even if its glyph editor remains open.
    var valid: bool = not command_pending and is_ready() and \
        not layout_pending and not timeline_model_pending and \
        int(current_state.get("revision",-1)) == timeline_model_revision and \
        native_score_piece_fingerprint == \
            str(current_state.get("piece_fingerprint",""))
    if not valid:
        return {"accepted":false,
            "message":"Wait for the current score operation to finish, then try again."}
    var payload: Dictionary = {"source_id":source_id,"finger":finger}
    if not native_score_piece_fingerprint.is_empty():
        payload["fingerprint"] = native_score_piece_fingerprint
    return {"accepted":true,"operation":"fingering.correct",
        "payload":payload}



func matches_ready_source(intent: Dictionary) -> bool:
    # Public, identity-bound readiness port. Consumers never inspect
    # fingerprint or revision storage directly.
    return is_ready() and _loaded and \
        _fingerprint == str(intent.get("fingerprint","")) and \
        revision == int(intent.get("revision",-1)) and \
        rendered_revision == revision and \
        str(_state.get("hand","")) == str(intent.get("hand",""))


func update_context(state: Dictionary, now_ms: int) -> void:
    var loaded: bool = bool(state.get("loaded",false))
    var next_revision: int = int(state.get("revision",0))
    var fingerprint: String = str(state.get("piece_fingerprint",""))
    var changed: bool = next_revision != revision or loaded != _loaded or fingerprint != _fingerprint
    _state = state.duplicate(true)
    _loaded = loaded
    _fingerprint = fingerprint
    if changed:
        _last_native_failure = ""
        _retry_attempted = false
        _identical_failure_repeats = 0
        revision = next_revision
        _generation += 1
        if not _reset_assets():
            return
        _preparing_since_ms = now_ms if _loaded else -1
        if _loaded:
            request_layout()
    if str(_state.get("phase","")) == "loading" and is_ready():
        # A busy action port may drop an intent. The next backend loading poll
        # repeats it, just as the accepted snapshot presentation path does.
        action_requested.emit({"action":"score_ready","revision":revision})

func adopt_prepared(state: Dictionary, prepared_renderer, prepared_layout: Dictionary) -> void:
    # The exact future score was compiled before the current take ended.
    # Reuse it without clearing the viewport or requesting the same ink.
    _generation += 1
    _requests.clear()
    _renderer = prepared_renderer
    _loaded = bool(state.get("loaded",false))
    _fingerprint = str(state.get("piece_fingerprint",""))
    _state = state.duplicate(true)
    revision = int(state.get("revision",-1))
    _layout = prepared_layout.duplicate(true)
    layout_revision = revision
    requested_layout_revision = revision
    timeline_model_revision = revision
    rendered_revision = revision
    _published_retained_generation = _renderer.retained_generation()
    native_score_piece_fingerprint = _fingerprint
    _retained_started_ms = -1
    _preparing_since_ms = -1
    score_error = ""
    _last_native_failure = ""
    _retry_attempted = false
    _identical_failure_repeats = 0
    _renderer.visible = true
    if _renderer.has_signal("retained_ink_compiled") and not \
            _renderer.is_connected("retained_ink_compiled",_finish_native_score):
        _renderer.connect("retained_ink_compiled",_finish_native_score)
    if is_instance_valid(_feedback):
        _feedback.bind_score(_renderer,revision)
        _feedback.present(_state)
    # Reset source-ID-scoped hit overlays without hiding the already
    # compiled notation or blanking the score viewport.
    assets_invalidated.emit(revision)
    layout_published.emit(revision,layout_snapshot())
    score_published.emit(revision)
    _publish_status()


func layout_snapshot() -> Dictionary:
    return _layout.duplicate(true)

func is_ready() -> bool:
    return score_error.is_empty() and _loaded and is_instance_valid(_renderer) and bool(_renderer.native_ready) and \
        (not _renderer.has_method("retained_ready") or _renderer.retained_ready()) and \
        layout_revision == revision and timeline_model_revision == revision and \
        rendered_revision == revision and \
        _published_retained_generation == _renderer.retained_generation()

## Source-bound measurement port. Only the owner that publishes the ready
## native engraving may supply its physical rest/header clearance to the
## musical scheduling contract. Presentation controls never inspect a
## mutable stage tree or a half-compiled layout.
func continuation_geometry() -> Dictionary:
    if not is_ready() or not _renderer.has_method("short_rest_geometry"):
        return {}
    return _renderer.short_rest_geometry()


func status() -> Dictionary:
    var ready: bool = is_ready()
    var stalled: bool = _loaded and _preparing_since_ms != -1 and \
        Time.get_ticks_msec() - _preparing_since_ms >= SLOW_PREPARATION_MS
    var text := ""
    if not score_error.is_empty():
        text = "Unable to display sheet music:\n"+score_error
    elif _loaded:
        if layout_pending or layout_revision != revision:
            text = "Preparing notation geometry…"
        else:
            text = "Compiling sheet music…"
    else:
        text = "Choose a piece to begin"
    return {"ready":ready,"visible":not ready,"text":text,"error":score_error,
        "retry_visible":not ready and (not score_error.is_empty() or stalled),
        "browse_visible":not ready and (not _loaded or not score_error.is_empty() or stalled)}

func poll(now_ms: int) -> void:
    if not _loaded or not score_error.is_empty():
        return
    if timeline_model_revision == revision and rendered_revision != revision and \
            _retained_started_ms >= 0 and \
            now_ms - _retained_started_ms >= RETAINED_INK_TIMEOUT_MS:
        _fail("Retained notation did not finish compiling. Retry the score.")

func pending_id(kind: String) -> int:
    return int(_requests.get(kind,{}).get("id",-1))

func fail(message: String) -> void:
    _fail(message)

func finish_native_score() -> void:
    _finish_native_score()

func request_layout() -> bool:
    if layout_pending or not _loaded or not score_error.is_empty():
        return false
    requested_layout_revision = revision
    _begin_request("bundle","score.bundle",90.0)
    return true

func retry(now_ms: int) -> bool:
    if not _loaded:
        return false
    # Explicit Retry cancels a pending layout as well as failed attempts.
    # Persist the prior raw error across _reset_assets() for exact failure
    # comparison, but never carry it into a different score revision.
    _retry_attempted = true
    _generation += 1
    if not _reset_assets():
        return false
    _preparing_since_ms = now_ms
    return request_layout()

func request_start_result(kind: String, request_id: int, error: int, now_ms: int) -> void:
    if error == OK:
        return
    var request: Dictionary = _take_request(kind,request_id)
    if request.is_empty():
        return
    if not _request_is_current(request):
        _drain_stale(kind,now_ms)
        return
    _fail("Cannot request the complete score bundle from the practice engine")

func complete_response(kind: String, request_id: int, code: int,
        body: PackedByteArray, now_ms: int) -> void:
    var request: Dictionary = _take_request(kind,request_id)
    if request.is_empty():
        return
    if not _request_is_current(request):
        _drain_stale(kind,now_ms)
        return
    if kind != "bundle":
        _fail("Unknown score bundle operation")
        return
    _complete_bundle(code,body,now_ms)

func _begin_request(kind: String, path: String, timeout: float) -> void:
    _next_request_id += 1
    _requests[kind] = {"id":_next_request_id,"generation":_generation,
        "revision":revision,"fingerprint":_fingerprint}
    request_requested.emit(kind,_next_request_id,path,timeout)

func _take_request(kind: String, request_id: int) -> Dictionary:
    var request: Dictionary = _requests.get(kind,{})
    if request.is_empty() or int(request["id"]) != request_id:
        return {}
    _requests.erase(kind)
    return request

func _request_is_current(request: Dictionary) -> bool:
    return _loaded and int(request["generation"]) == _generation and \
        int(request["revision"]) == revision and str(request["fingerprint"]) == _fingerprint

func _drain_stale(_kind: String, _now_ms: int) -> void:
    request_layout()

func _complete_bundle(code: int, body: PackedByteArray, now_ms: int) -> void:
    if code != 0:
        _fail(_command_failure(code,body))
        return
    var bundle: Variant = _decode_json(body)
    if not bundle is Dictionary:
        _fail("Practice engine returned no source-bound score bundle")
        return
    var layout: Variant = bundle.get("layout")
    var model: Variant = bundle.get("model")
    var source_ids: Variant = bundle.get("source_note_ids")
    # Reject both halves before touching a retained renderer.
    if (str(bundle.get("status","")) != "ready" or
            int(bundle.get("revision",-1)) != revision or
            str(bundle.get("fingerprint","")) != _fingerprint or
            str(bundle.get("hand","")) != str(_state.get("hand","")) or
            str(bundle.get("stage_key","")).is_empty() or
            not source_ids is Array or source_ids.is_empty() or
            not layout is Dictionary or not layout.has("anchors") or
            int(layout.get("revision",-1)) != revision or
            not model is Dictionary or int(model.get("revision",-1)) != revision):
        _fail("Score bundle source, revision, notation or MIDI identity differs")
        return
    if not is_instance_valid(_renderer):
        return
    var installed: Dictionary = NativeScoreAssets.install(_renderer, layout)
    if not bool(installed.get("ok",false)):
        _fail(str(installed.get("error","Authentic engraving unavailable")))
        return
    if not _renderer.load_score(model):
        _fail(str(_renderer.failure_reason))
        return
    _layout = installed["layout"]
    layout_revision = revision
    timeline_model_revision = revision
    native_score_piece_fingerprint = _fingerprint
    _retained_started_ms = now_ms
    _renderer.visible = true
    if is_instance_valid(_feedback):
        _feedback.bind_score(_renderer,revision)
        _feedback.present(_state.duplicate(true))
    layout_published.emit(revision,layout_snapshot())
    _publish_status()
    _finish_native_score()

func _finish_native_score() -> void:
    if layout_revision != revision or timeline_model_revision != revision or \
            not is_instance_valid(_renderer) or not bool(_renderer.native_ready):
        return
    # Publishing now would let the engine start while a future source copy
    # is still waiting to record its CanvasItem command buffer. All basic
    # source and silence segments must exist before score_ready is sent.
    if _renderer.has_method("retained_ready") and not _renderer.retained_ready():
        return
    # Compilation completes in draw, while readiness publication is deferred.
    # Only this acknowledgement can expose a ready generation to the UI and
    # admission; a getter must not outrun its matching status notification.
    _published_retained_generation = _renderer.retained_generation()
    if rendered_revision == revision:
        # A resize or staff focus recompiled this revision's strips. Status
        # published while they compiled said "Compiling"; clear it.
        _publish_status()
        return
    rendered_revision = revision
    _preparing_since_ms = -1
    _retained_started_ms = -1
    score_error = ""
    _last_native_failure = ""
    _retry_attempted = false
    _identical_failure_repeats = 0
    _publish_status()
    score_published.emit(revision)
    if str(_state.get("phase","")) == "loading" and \
            int(_state.get("awaiting_score_revision",-1)) == revision and is_ready():
        action_requested.emit({"action":"score_ready","revision":revision})

func _reset_assets() -> bool:
    # Supersede both in-flight operations immediately on score change or Retry.
    # The queue cancels the old adapter when its replacement is dispatched.
    _requests.clear()
    if not _hide_renderer():
        # Keep exposed native ink and its feedback binding alive. No new
        # atlas/model may overwrite the source whose journal could not close.
        _fail(str(_renderer.failure_reason),false)
        return false
    _retained_started_ms = -1
    _layout.clear()
    layout_revision = -1
    timeline_model_revision = -1
    rendered_revision = -1
    _published_retained_generation = -1
    native_score_piece_fingerprint = ""
    score_error = ""
    assets_invalidated.emit(revision)
    _publish_status()
    return true

func _hide_renderer() -> bool:
    if is_instance_valid(_renderer):
        if not _renderer.clear_score():
            return false
        # Loading/failure revokes score ink, not the endless empty staff.
        _renderer.visible = true
        if is_instance_valid(_feedback):
            _feedback.bind_score(_renderer,-1)
    return true

func _fail(message: String, release_renderer: bool = true) -> void:
    push_error("SCORE_ASSET_FAILURE: " + message)
    var repeated: bool = _retry_attempted and \
        message == _last_native_failure and not message.is_empty()
    _identical_failure_repeats = (
        _identical_failure_repeats+1 if repeated else 0)
    _last_native_failure = message
    _retry_attempted = false
    score_error = message
    if repeated:
        score_error += ("\nRetry reproduced the same engraving failure " +
            "(%d repeat%s). Inspect SCORE_ASSET_FAILURE or choose music." % [
                _identical_failure_repeats,
                "" if _identical_failure_repeats == 1 else "s"])
    _retained_started_ms = -1
    rendered_revision = -1
    timeline_model_revision = -1
    if release_renderer and not _hide_renderer():
        var preservation: String = str(_renderer.failure_reason)
        if not preservation.is_empty() and not score_error.contains(preservation):
            score_error += "\n"+preservation
    score_failed.emit(score_error)
    _publish_status()

func _publish_status() -> void:
    status_changed.emit(status())

static func _decode_json(body: PackedByteArray) -> Variant:
    if body.is_empty():
        return null
    var document := JSON.new()
    if document.parse(body.get_string_from_utf8()) != OK:
        return null
    return document.data

static func _command_failure(code: int, body: PackedByteArray) -> String:
    var response: Variant = _decode_json(body)
    if response is Dictionary:
        return str(response.get("error","Command failed (status %d)" % code))
    if code == 0:
        return "Practice engine unavailable. Start Piano Teacher with ./run.sh"
    return "In-process practice command failed (status %d)" % code
