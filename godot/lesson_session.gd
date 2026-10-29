extends RefCounted
# Owns the lesson overview cache and request lifecycle, independently of HTTP/UI.
signal request_requested
signal overview_changed(values: Dictionary)
signal request_failed(message: String)
const RETRY_MS := 1000
var pending := false
var _loaded := false
var _fingerprint := ""
var _generation := 0
var _requested_generation := -1
var _requested_fingerprint := ""
var _retry_after_ms := 0
var _overview: Dictionary = {}
var _needs_refresh := true

func update_context(state: Dictionary, now_ms: int) -> void:
    var loaded: bool = bool(state.get("loaded",false))
    var fingerprint: String = str(state.get("piece_fingerprint",""))
    if loaded != _loaded or fingerprint != _fingerprint:
        _loaded = loaded
        _fingerprint = fingerprint
        invalidate()
    ensure_current(now_ms)

func snapshot() -> Dictionary:
    return _overview.duplicate(true)

func invalidate() -> void:
    _generation += 1
    _overview.clear()
    _needs_refresh = true
    _retry_after_ms = 0
    overview_changed.emit({})

func ensure_current(now_ms: int) -> void:
    if _loaded and _needs_refresh and not pending and now_ms >= _retry_after_ms:
        _begin_request()

func refresh(now_ms: int) -> void:
    _needs_refresh = true
    _retry_after_ms = now_ms
    ensure_current(now_ms)

func _begin_request() -> void:
    pending = true
    _requested_generation = _generation
    _requested_fingerprint = _fingerprint
    request_requested.emit()

func complete_response(values: Variant, error: String, now_ms: int) -> void:
    if not pending: return
    pending = false
    if _requested_generation != _generation or _requested_fingerprint != _fingerprint or not _loaded:
        ensure_current(now_ms)
        return
    if error.is_empty() and not values is Dictionary:
        error = "Unable to read lesson overview"
    if not error.is_empty():
        _retry_after_ms = now_ms + RETRY_MS
        request_failed.emit(error)
        return
    if str(values.get("piece_fingerprint","")) != _fingerprint:
        _retry_after_ms = now_ms + RETRY_MS
        return
    _overview = values.duplicate(true)
    _needs_refresh = false
    _retry_after_ms = 0
    overview_changed.emit(snapshot())
