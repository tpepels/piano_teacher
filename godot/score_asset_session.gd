extends RefCounted
## Owns one revision's native layout/atlas/model publication and HTTP lifecycle.
## Borrows actual renderer/feedback components; retains no Main, widgets, HTTP
## nodes or callbacks. Transport adapters echo the emitted request ID on every
## start result/response. A stale reply drains its slot without publishing data.
signal request_requested(kind: String, request_id: int, path: String, timeout_seconds: float)
signal assets_invalidated(revision: int)
signal layout_published(revision: int, values: Dictionary)
signal score_published(revision: int)
signal score_failed(message: String)
signal status_changed(values: Dictionary)
signal action_requested(command: Dictionary)

const MODEL_RETRY_MS := 2000
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
var _next_request_id := 0
# Exactly two request slots, matching the two existing HTTPRequest endpoints.
var _requests: Dictionary = {}

func _init(renderer, native_feedback = null) -> void:
    _renderer = renderer
    _feedback = native_feedback

func update_context(state: Dictionary, _now_ms: int) -> void:
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
        layout_revision == revision and timeline_model_revision == revision and \
        rendered_revision == revision

func status() -> Dictionary:
    var ready: bool = is_ready()
    var text := ""
    if not score_error.is_empty():
        text = "Unable to display sheet music:\n"+score_error
    elif _loaded:
        text = "Preparing sheet music…"
    else:
        text = "Choose a piece to begin"
    return {"ready":ready,"visible":not ready,"text":text,
        "retry_visible":not ready and not score_error.is_empty(),
        "browse_visible":not ready and score_error.is_empty() and not _loaded}

func poll(now_ms: int) -> void:
    if _loaded and score_error.is_empty() and timeline_model_revision != revision and \
            not timeline_model_pending and now_ms >= timeline_model_retry_after_ms:
        request_model()

func request_layout() -> bool:
    if layout_pending or not _loaded:
        return false
    requested_layout_revision = revision
    _begin_request("layout","/score/layout?native=1",90.0)
    return true

func request_model() -> bool:
    # Semantic source must wait for this revision's actual authentic atlas.
    if timeline_model_pending or not _loaded or not score_error.is_empty() or \
            layout_revision != revision or not is_instance_valid(_renderer) or \
            not _renderer.glyphs.ready():
        return false
    _begin_request("model","/score/model",5.0)
    return true

func retry(_now_ms: int) -> bool:
    if not _loaded or layout_pending:
        return false
    _generation += 1
    _reset_assets()
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
    if code != 200:
        _fail(_http_failure(code,body))
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
    if not _renderer.set_verovio_glyphs(parsed.get("native_glyphs",{}),
            parsed.get("native_note_templates",{}),parsed.get("native_tie_templates",{}),
            parsed.get("native_chord_templates",{}),parsed.get("native_beam_fragments",{}),
            parsed.get("native_tuplet_fragments",{}),parsed.get("native_slur_fragments",{}),
            parsed.get("native_required_slur_pairs",[]),bool(parsed.get("native_slurs_complete",false)),
            parsed.get("native_required_beam_groups",[]),bool(parsed.get("native_beams_complete",false))):
        _fail(str(_renderer.failure_reason))
        return
    for key in ASSET_KEYS:
        parsed.erase(key)
    _layout = parsed
    layout_revision = revision
    timeline_model_revision = -1
    score_error = ""
    layout_published.emit(revision,layout_snapshot())
    _publish_status()
    request_model()

func _complete_model(code: int, body: PackedByteArray, now_ms: int) -> void:
    if not is_instance_valid(_renderer) or layout_revision != revision or not score_error.is_empty():
        return
    var candidate: Variant = _decode_json(body)
    if code == 200 and candidate is Dictionary:
        if int(candidate.get("revision",-1)) != revision:
            return
        if not _renderer.load_score(candidate):
            _fail(str(_renderer.failure_reason))
            return
        native_score_piece_fingerprint = _fingerprint
        timeline_model_revision = revision
        _renderer.visible = true
        if is_instance_valid(_feedback):
            _feedback.bind_score(_renderer,revision)
            _feedback.present(_state.duplicate(true))
        _finish_native_score()
        return
    _retry_model(now_ms,"Score model unavailable; retrying")

func _finish_native_score() -> void:
    if layout_revision != revision or timeline_model_revision != revision or \
            not is_instance_valid(_renderer) or not bool(_renderer.native_ready):
        return
    rendered_revision = revision
    score_error = ""
    _publish_status()
    score_published.emit(revision)
    if str(_state.get("phase","")) == "loading" and \
            int(_state.get("awaiting_score_revision",-1)) == revision and is_ready():
        action_requested.emit({"action":"score_ready","revision":revision})

func _retry_model(now_ms: int, notice: String) -> void:
    timeline_model_retry_after_ms = now_ms+MODEL_RETRY_MS
    if is_instance_valid(_renderer):
        _renderer.notice = notice
        _renderer.queue_redraw()
    _publish_status()

func _reset_assets() -> void:
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
    score_error = message
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

static func _http_failure(code: int, body: PackedByteArray) -> String:
    var response: Variant = _decode_json(body)
    if response is Dictionary:
        return str(response.get("error","Request failed (HTTP %d)" % code))
    if code == 0:
        return "Practice engine unavailable. Start Piano Teacher with ./run.sh"
    return "Practice engine request failed (HTTP %d)" % code
