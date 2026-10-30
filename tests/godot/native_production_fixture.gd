extends "res://main.gd"
# Offline wire fixture. Production builds the view, binds authentic assets,
# accepts the score model and computes readiness through its real handlers.
# Only outbound requests are suppressed; renderer and transport remain real.

func _ready() -> void:
    _build_interface()
    _navigate("practice")
    resized.connect(_update_responsive_layout)
    _update_responsive_layout()
    set_process(false)

func _request_layout() -> void: pass
func _request_timeline_model() -> void: pass
func _request_library() -> void: pass
func _request_settings() -> void: pass
func _request_devices() -> void: pass
func _request_lesson() -> void: pass
func _poll() -> void: pass
func _send_post(_path: String, _payload: Dictionary) -> void: pass

func load_native_fixture(folder: String) -> String:
    if practice_view.stage.renderer == null:
        return "Production must construct the native notation view unconditionally"
    if practice_view.stage.renderer.get_script().resource_path != "res://notation/native/view.gd":
        return "Practice must use the production native notation view"
    var payload: Variant = JSON.parse_string(FileAccess.get_file_as_string(
        folder.path_join("native.json")))
    if not payload is Dictionary:
        return "Missing engine-prepared native.json fixture"
    # Drive the actual revision-aware owner. The old Main fields were
    # removed when HTTP score loading moved into ScoreAssetSession.
    # This offline fixture supplies responses only; native rendering is real.
    last_state = payload.state.duplicate(true)
    last_state["loaded"] = true
    last_state["revision"] = int(payload.model.revision)
    last_state["piece_fingerprint"] = str(last_state.get(
        "piece_fingerprint", "visual-production-fixture"))
    score_session.update_context(last_state, Time.get_ticks_msec())
    var layout_id: int = score_session.pending_id("layout")
    if layout_id < 0:
        return "Score session did not request authentic layout"
    score_session.complete_response("layout", layout_id, 200,
        JSON.stringify(payload.layout).to_utf8_buffer(), Time.get_ticks_msec())
    var model_id: int = score_session.pending_id("model")
    if model_id < 0:
        return "Score session did not request semantic model after layout"
    score_session.complete_response("model", model_id, 200,
        JSON.stringify(payload.model).to_utf8_buffer(), Time.get_ticks_msec())
    if not has_method("_native_score_ready") or not call("_native_score_ready"):
        return "Production native score is not ready: " + str(practice_view.stage.renderer.failure_reason)
    if practice_view.stage.renderer.timeline.notes.is_empty():
        return "Production loaded no source notes"
    return ""
