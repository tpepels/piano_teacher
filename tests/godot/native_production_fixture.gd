extends "res://main.gd"
# Offline typed-queue fixture. Production builds the view, binds authentic assets,
# accepts the score model and computes readiness through its real handlers.
# Only outbound requests are suppressed; renderer and transport remain real.

class OfflineRequest extends RefCounted:
    var timeout := 5.0
    func request(_operation: String, _payload: Dictionary = {}) -> int:
        return OK

func _ready() -> void:
    _build_interface()
    action_request = OfflineRequest.new()
    startup_last_music_checked = true
    frame_coordinator = PracticeFrameCoordinator.new(
        practice_view,settings_view,lesson_view,lesson_session,
        null,frame_meter)
    state_presenter = PracticeStatePresenter.new(
        practice_view,settings_view,lesson_view,lesson_session,
        null)
    command_failure_presenter = CommandFailurePresenter.new(
        library_view,practice_view,settings_view,home_view)
    command_success_presenter = CommandSuccessPresenter.new(
        library_view,practice_view,settings_view,lesson_session)
    command_success_effects = CommandSuccessEffects.new(command_success_presenter)
    command_success_effects.publish_state.connect(_on_state)
    command_success_effects.navigate_practice.connect(_navigate)
    command_success_effects.request_settings.connect(_request_settings)
    command_success_effects.request_library.connect(_request_library)
    command_success_effects.request_library_health.connect(_request_library_health)
    command_success_effects.refresh_score.connect(_refresh_score_status)
    metronome_frame = MetronomeFrameCoordinator.new(
        settings_view,practice_view,visual_transport_clock,
        _transport_beat_at,_count_tick,_raw_click)
    # Source fixture must route score_ready through a real configured
    # command coordinator, even though its outbound transport is stubbed.
    # The old unconfigured coordinator dereferenced a null practice view.
    command_coordinator.configure(practice_view,settings_view,metronome_frame,
        score_flow,visual_transport_clock,action_request,command_failure_presenter)
    command_coordinator.succeeded.connect(command_success_effects.apply)
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

func load_native_fixture(folder: String) -> String:
    if practice_view.stage.renderer == null:
        return "Production must construct the native notation view unconditionally"
    if practice_view.stage.renderer.get_script().resource_path != "res://notation/native/view.gd":
        return "Practice must use the production native notation view"
    var payload: Variant = JSON.parse_string(FileAccess.get_file_as_string(
        folder.path_join("native.json")))
    if not payload is Dictionary:
        return "Missing engine-prepared native.json fixture"
    # Drive the actual revision-aware owner with typed worker responses.
    # This fixture supplies responses only; native rendering is real.
    last_state = payload.state.duplicate(true)
    last_state["loaded"] = true
    last_state["revision"] = int(payload.model.revision)
    last_state["piece_fingerprint"] = str(last_state.get(
        "piece_fingerprint", "visual-production-fixture"))
    _on_state(0,JSON.stringify(last_state).to_utf8_buffer(),Time.get_ticks_msec())
    if score_session.pending_id("layout") < 0:
        score_session.retry(Time.get_ticks_msec())
    var layout_id: int = score_session.pending_id("layout")
    if layout_id < 0:
        return "Score session did not request authentic layout"
    score_session.complete_response("layout", layout_id, 0,
        JSON.stringify(payload.layout).to_utf8_buffer(), Time.get_ticks_msec())
    var model_id: int = score_session.pending_id("model")
    if model_id < 0:
        return "Score session did not request semantic model after layout"
    score_session.complete_response("model", model_id, 0,
        JSON.stringify(payload.model).to_utf8_buffer(), Time.get_ticks_msec())
    # Readiness includes real retained CanvasItem compilation, which occurs
    # after drawing. Never certify only the synchronous semantic load.
    var deadline := Time.get_ticks_msec() + 5000
    while not _native_score_ready() and score_error.is_empty() and Time.get_ticks_msec() < deadline:
        await get_tree().process_frame
    if not has_method("_native_score_ready") or not call("_native_score_ready"):
        return "Production native score is not ready: " + str(practice_view.stage.renderer.failure_reason)
    if practice_view.stage.renderer.timeline.notes.is_empty():
        return "Production loaded no source notes"
    return ""
