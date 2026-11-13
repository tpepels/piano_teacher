extends Node
## Owns report request/page identity without a Main or engine backreference.
var _request: Node
var _view: Control
var _fingerprint := ""
var _learner := ""
var _pending := false
var _scope := 0
var _cursor := ""
var _next_cursor := ""
var _previous: Array[String] = []
var _sent_fingerprint := ""
var _sent_learner := ""

func configure(request: Node, view: Control) -> void:
    _request = request
    _view = view
    if not request.request_completed.is_connected(on_report):
        request.request_completed.connect(on_report)
    view.query_requested.connect(_query)

func update_context(fingerprint: String, learner: String = "") -> void:
    var changed: bool = (not learner.is_empty() and learner != _learner) or (
        _scope == 1 and fingerprint != _fingerprint)
    _fingerprint = fingerprint
    if not learner.is_empty():
        _learner = learner
    if changed:
        invalidate()

func invalidate() -> void:
    if _request != null:
        _request.cancel_request()
    _pending = false
    _cursor = ""
    _next_cursor = ""
    _previous.clear()
    if _view != null:
        _view.present_message("History or piece changed. Refresh statistics.")
        _view.present_page(false, false, false, 1)

func _query(scope: int, action: String) -> void:
    if scope != _scope:
        _scope = scope
        invalidate()
    elif _pending:
        return
    if action == "next":
        if _next_cursor.is_empty():
            return
        _previous.append(_cursor)
        _cursor = _next_cursor
    elif action == "previous":
        if _previous.is_empty():
            return
        _cursor = _previous.pop_back()
    else:
        _cursor = ""
        _previous.clear()
    if _scope == 1 and _fingerprint.is_empty():
        _view.present_message("Choose a piece, then Refresh statistics.")
        return
    var payload := {"version": 1, "limit": 250}
    if _scope == 1:
        payload["fingerprint"] = _fingerprint
    if not _cursor.is_empty():
        payload["cursor"] = _cursor
    _sent_fingerprint = _fingerprint
    _sent_learner = _learner
    _pending = true
    _view.present_message("Loading recorded practice…")
    _view.present_page(true, false, false, _previous.size()+1)
    if _request.request("learning.statistics", payload) != OK:
        _pending = false
        _view.present_message("Cannot read statistics. Refresh to retry.")
        _view.present_page(false, not _previous.is_empty(), false, _previous.size()+1)

func on_report(code: int, body: PackedByteArray) -> void:
    if not _pending:
        return
    _pending = false
    if _sent_learner != _learner or (_scope == 1 and _sent_fingerprint != _fingerprint):
        invalidate()
        return
    var report: Variant = JSON.parse_string(body.get_string_from_utf8())
    if code != 0 or not report is Dictionary:
        _view.present_message(str(report.get("error", "Cannot read statistics. Refresh to retry."))
            if report is Dictionary else "Cannot read statistics. Refresh to retry.")
        _view.present_page(false, not _previous.is_empty(), false, _previous.size()+1)
        return
    if int(report.get("schema_version", 0)) != 2:
        _view.present_message("Unsupported statistics report version. Refresh after updating the application.")
        _view.present_page(false, false, false, 1)
        return
    if (_scope == 1 and str(report.get("fingerprint", "")) != _fingerprint) or (
        report.has("learner_id") and not _learner.is_empty() and str(report["learner_id"]) != _learner):
        invalidate()
        return
    var next_value: Variant = report.get("query", {}).get("next_cursor")
    _next_cursor = "" if next_value == null else str(next_value)
    _view.present_report(report)
    _view.present_page(false, not _previous.is_empty(), not _next_cursor.is_empty(), _previous.size()+1)
