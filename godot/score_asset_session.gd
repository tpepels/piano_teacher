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

const MODEL_RETRY_MS := 2000
const MODEL_MAX_ATTEMPTS := 3
const MODEL_TIMEOUT_SECONDS := 30.0
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
var timeline_model_retry_after_ms := 0
var native_score_piece_fingerprint := ""
var score_error := ""
var layout_pending: bool:
    get: return _requests.has("layout")
var timeline_model_pending: bool:
    get: return _requests.has("model")
var score_layout: Dictionary:
    get: return layout_snapshot()

var _renderer
var _feedback
var _loaded := false
var _fingerprint := ""
var _state: Dictionary = {}
var _layout: Dictionary = {}
var _generation := 0
var _model_failures := 0
var _retained_started_ms := -1
var _preparing_since_ms := -1
var _next_request_id := 0
# Exactly two in-process command slots: native layout and semantic model.
var _requests: Dictionary = {}

func _init(renderer, native_feedback = null) -> void:
    _renderer = renderer
    _feedback = native_feedback
    if is_instance_valid(renderer) and renderer.has_signal("retained_ink_compiled"):
        renderer.connect("retained_ink_compiled",_finish_native_score)

func update_context(state: Dictionary, now_ms: int) -> void:
    var loaded: bool = bool(state.get("loaded",false))
    var next_revision: int = int(state.get("revision",0))
    var fingerprint: String = str(state.get("piece_fingerprint",""))
    var changed: bool = next_revision != revision or loaded != _loaded or fingerprint != _fingerprint
    _state = state.duplicate(true)
    _loaded = loaded
    _fingerprint = fingerprint
    if changed:
        revision = next_revision
        _generation += 1
        _reset_assets()
        _preparing_since_ms = now_ms if _loaded else -1
        if _loaded:
            request_layout()
    if str(_state.get("phase","")) == "loading" and is_ready():
        # A busy action port may drop an intent. The next backend loading poll
        # repeats it, just as Main's current _on_state path does.
        action_requested.emit({"action":"score_ready","revision":revision})

func layout_snapshot() -> Dictionary:
    return _layout.duplicate(true)

func is_ready() -> bool:
    return _loaded and is_instance_valid(_renderer) and bool(_renderer.native_ready) and \
        (not _renderer.has_method("retained_ready") or _renderer.retained_ready()) and \
        layout_revision == revision and timeline_model_revision == revision and \
        rendered_revision == revision

func status() -> Dictionary:
    var ready: bool = is_ready()
    var stalled: bool = _loaded and _preparing_since_ms >= 0 and \
        Time.get_ticks_msec() - _preparing_since_ms >= SLOW_PREPARATION_MS
    var text := ""
    if not score_error.is_empty():
        text = "Unable to display sheet music:\n"+score_error
    elif _loaded:
        if layout_pending or layout_revision != revision:
            text = "Preparing notation geometry…"
        elif timeline_model_pending or timeline_model_revision != revision:
            text = "Preparing note timing and positions…"
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
    if timeline_model_revision != revision and not timeline_model_pending and \
            now_ms >= timeline_model_retry_after_ms:
        request_model()
    elif timeline_model_revision == revision and rendered_revision != revision and \
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
    if layout_pending or not _loaded:
        return false
    requested_layout_revision = revision
    _begin_request("layout","score.native_layout",90.0)
    return true

func request_model() -> bool:
    # Semantic source must wait for this revision's actual authentic atlas.
    if timeline_model_pending or not _loaded or not score_error.is_empty() or \
            layout_revision != revision or not is_instance_valid(_renderer) or \
            not _renderer.glyphs.ready():
        return false
    _begin_request("model","score.semantic",MODEL_TIMEOUT_SECONDS)
    return true

func retry(now_ms: int) -> bool:
    if not _loaded:
        return false
    # Explicit Retry cancels a pending layout as well as failed attempts.
    _generation += 1
    _reset_assets()
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
    if kind == "layout":
        _fail("Cannot request score geometry from the practice engine")
    else:
        _retry_model(now_ms,"Cannot load semantic score")

func complete_response(kind: String, request_id: int, code: int,
        body: PackedByteArray, now_ms: int) -> void:
    var request: Dictionary = _take_request(kind,request_id)
    if request.is_empty():
        return
    if not _request_is_current(request):
        _drain_stale(kind,now_ms)
        return
    if kind == "layout":
        _complete_layout(code,body)
    else:
        _complete_model(code,body,now_ms)

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

func _drain_stale(kind: String, now_ms: int) -> void:
    if kind == "layout":
        request_layout()
    else:
        poll(now_ms)

func _complete_layout(code: int, body: PackedByteArray) -> void:
    if code != 0:
        _fail(_command_failure(code,body))
        return
    var parsed: Variant = _decode_json(body)
    if not parsed is Dictionary or not parsed.has("anchors"):
        _fail("The engraving engine returned invalid note positions")
        return
    if parsed.has("revision") and int(parsed["revision"]) != revision:
        # The server advanced before its state response arrived. Its normal
        # revision poll will invalidate this request and request that layout.
        return
    if not is_instance_valid(_renderer):
        return
    var installed: Dictionary = NativeScoreAssets.install(_renderer, parsed)
    if not bool(installed.get("ok",false)):
        _fail(str(installed.get("error","Authentic engraving unavailable")))
        return
    _layout = installed["layout"]
    layout_revision = revision
    timeline_model_revision = -1
    score_error = ""
    layout_published.emit(revision,layout_snapshot())
    _publish_status()
    request_model()

func _complete_model(code: int, body: PackedByteArray, now_ms: int) -> void:
    if not is_instance_valid(_renderer) or layout_revision != revision or not score_error.is_empty():
        return
    if code != 0:
        var message: String = _command_failure(code,body)
        if code == 3 and message.contains("deadline"):
            _retry_model(now_ms,message)
        else:
            _fail(message)
        return
    var candidate: Variant = _decode_json(body)
    if not candidate is Dictionary:
        _fail("Practice engine returned an invalid semantic score")
        return
    if int(candidate.get("revision",-1)) != revision:
        _retry_model(now_ms,"Semantic score revision changed during loading")
        return
    if not _renderer.load_score(candidate):
        _fail(str(_renderer.failure_reason))
        return
    native_score_piece_fingerprint = _fingerprint
    timeline_model_revision = revision
    _model_failures = 0
    _retained_started_ms = now_ms
    _renderer.visible = true
    if is_instance_valid(_feedback):
        _feedback.bind_score(_renderer,revision)
        _feedback.present(_state.duplicate(true))
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
    if rendered_revision == revision:
        return
    rendered_revision = revision
    _preparing_since_ms = -1
    _retained_started_ms = -1
    score_error = ""
    _publish_status()
    score_published.emit(revision)
    if str(_state.get("phase","")) == "loading" and \
            int(_state.get("awaiting_score_revision",-1)) == revision and is_ready():
        action_requested.emit({"action":"score_ready","revision":revision})

func _retry_model(now_ms: int, notice: String) -> void:
    _model_failures += 1
    if _model_failures >= MODEL_MAX_ATTEMPTS:
        _fail("Semantic score failed after %d attempts: %s" % [MODEL_MAX_ATTEMPTS, notice])
        return
    timeline_model_retry_after_ms = now_ms + MODEL_RETRY_MS * _model_failures
    if is_instance_valid(_renderer):
        _renderer.notice = "%s (attempt %d/%d)" % [notice, _model_failures + 1, MODEL_MAX_ATTEMPTS]
        _renderer.queue_redraw()
    _publish_status()

func _reset_assets() -> void:
    # Supersede both in-flight operations immediately on score change or Retry.
    # The queue cancels the old adapter when its replacement is dispatched.
    _requests.clear()
    _model_failures = 0
    _retained_started_ms = -1
    _layout.clear()
    layout_revision = -1
    timeline_model_revision = -1
    rendered_revision = -1
    timeline_model_retry_after_ms = 0
    native_score_piece_fingerprint = ""
    score_error = ""
    _hide_renderer()
    assets_invalidated.emit(revision)
    _publish_status()

func _hide_renderer() -> void:
    if is_instance_valid(_renderer):
        _renderer.clear_score()
        _renderer.visible = false
        if is_instance_valid(_feedback):
            _feedback.bind_score(_renderer,-1)

func _fail(message: String) -> void:
    push_error("SCORE_ASSET_FAILURE: " + message)
    score_error = message
    _retained_started_ms = -1
    rendered_revision = -1
    timeline_model_revision = -1
    _hide_renderer()
    score_failed.emit(message)
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
