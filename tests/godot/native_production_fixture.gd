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
    if timeline_preview == null:
        return "Production must construct the native notation view unconditionally"
    if timeline_preview.get_script().resource_path != "res://notation/native/view.gd":
        return "Practice must use the production native notation view"
    var payload: Variant = JSON.parse_string(FileAccess.get_file_as_string(
        folder.path_join("native.json")))
    if not payload is Dictionary:
        return "Missing engine-prepared native.json fixture"
    revision = int(payload.model.revision)
    requested_layout_revision = revision
    last_state = payload.state.duplicate(true)
    _on_layout(0, 200, PackedStringArray(), JSON.stringify(payload.layout).to_utf8_buffer())
    _on_timeline_model(0, 200, PackedStringArray(), JSON.stringify(payload.model).to_utf8_buffer())
    if not has_method("_native_score_ready") or not call("_native_score_ready"):
        return "Production native score is not ready: " + str(timeline_preview.failure_reason)
    if timeline_preview.timeline.notes.is_empty():
        return "Production loaded no source notes"
    return ""
