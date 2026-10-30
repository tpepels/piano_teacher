extends SceneTree

class FixtureApp extends "res://main.gd":
    var raster_requests := 0
    var layout_requests := 0
    var commands: Array = []

    func _ready() -> void:
        _build_interface()
        _navigate("practice")
        _update_responsive_layout()
        set_process(false)
        # Test drives the real ScoreAssetSession without contacting HTTP.
        score_session.request_requested.connect(func(kind: String,
                _id: int, _path: String, _seconds: float):
            if kind == "layout":
                layout_requests += 1)

    func _poll() -> void:
        pass

    func _request_devices() -> void:
        pass

    func _request_settings() -> void:
        pass

    func _request_library() -> void:
        pass

    func _request_layout() -> void:
        layout_requests += 1

    func _request_score(_page: int) -> void:
        raster_requests += 1

    func _send_action(command: Dictionary) -> void:
        commands.append(command)

var failures: Array[String] = []

func check(ok: bool, message: String) -> void:
    if not ok:
        failures.append(message)
        print("NATIVE_PRODUCTION_FAIL:", message)

func _initialize() -> void:
    call_deferred("run")

func activate(app: Control, revision: int, phase: String = "loading") -> void:
    var state := {"loaded":true, "revision":revision, "phase":phase,
        "mode":"practice", "awaiting_score_revision":revision,
        "piece_fingerprint":"native-production-test"}
    app.last_state = state
    app.score_session.update_context(state, Time.get_ticks_msec())

func deliver_layout(app: Control, layout: Dictionary) -> void:
    var request_id: int = app.score_session.pending_id("layout")
    check(request_id > 0, "An actual layout request precedes the response")
    if request_id > 0:
        app.score_session.complete_response("layout", request_id, 200,
            JSON.stringify(layout).to_utf8_buffer(), Time.get_ticks_msec())

func deliver_model(app: Control, model: Dictionary) -> void:
    var request_id: int = app.score_session.pending_id("model")
    check(request_id > 0, "An actual semantic request precedes the response")
    if request_id > 0:
        app.score_session.complete_response("model", request_id, 200,
            JSON.stringify(model).to_utf8_buffer(), Time.get_ticks_msec())

func run() -> void:
    var payload: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
        OS.get_cmdline_user_args()[0]))
    var app := FixtureApp.new()
    root.add_child(app)
    check(app.practice_view.stage.renderer != null and
        app.practice_view.stage.renderer.get_script() == load("res://notation/native/view.gd"),
        "Production always creates the native view, including under retired switches")
    var retired_canvases := 0
    for node in app.find_children("*", "", true, false):
        var script = node.get_script()
        if script != null and script.resource_path in ["res://score_overlay.gd", "res://note_reactions.gd"]:
            retired_canvases += 1
    check(retired_canvases == 0, "Production never mounts retired page-coordinate drawing canvases")
    if app.practice_view.stage.renderer == null or not app.practice_view.stage.renderer.has_method("set_verovio_glyphs"):
        print("NATIVE_PRODUCTION_FAILURES:", failures.size())
        quit(1)
        return
    activate(app, int(payload.model.revision))
    # Missing authentic assets must fail visibly, without requesting page ink.
    var broken_assets: Dictionary = payload.layout.duplicate(true)
    broken_assets["native_glyphs"] = {}
    deliver_layout(app, broken_assets)
    check(not app.score_error.is_empty() and app.practice_view.stage.score_status_panel.visible,
        "Rejected assets expose a persistent score error")
    check(app.practice_view.start_button.disabled and app.rendered_revision != app.revision,
        "Rejected assets cannot enable Play or complete readiness")
    check(app.commands.is_empty() and app.raster_requests == 0,
        "Rejected assets never acknowledge readiness or fall back to PNG pages")
    var failed_state := {"loaded":true,"revision":app.revision,"phase":"ready",
        "mode":"practice","piece_fingerprint":"native-production-test"}
    app._on_state(0, 200, PackedStringArray(), JSON.stringify(failed_state).to_utf8_buffer())
    check(not app.score_error.is_empty() and app.practice_view.stage.score_status_panel.visible
        and app.practice_view.stage.score_retry_button.visible and app.practice_view.stage.score_status_label.text.contains(app.score_error),
        "State polling preserves the native preparation error and its Retry action")
    app.last_state = {"loaded":true,"mode":"learn","phase":"ready"}
    app._toggle_playing()
    check(app.commands.is_empty(), "Keyboard Play cannot start Learn before native readiness")
    app.commands.clear()
    app._retry_score()
    check(app.score_error.is_empty() and app.layout_requests == 1
        and app.layout_revision == -1 and app.rendered_revision == -1
        and not app.practice_view.stage.renderer.native_ready and not app.practice_view.stage.score_retry_button.visible,
        "Retry clears failed preparation and requests fresh native assets")
    app.last_state = {"loaded":true,"phase":"loading", "awaiting_score_revision":app.revision}
    deliver_layout(app, payload.layout)
    var stale: Dictionary = payload.model.duplicate(true)
    stale["revision"] = app.revision + 1
    deliver_model(app, stale)
    check(app.commands.is_empty() and app.rendered_revision != app.revision,
        "A newer model cannot complete the current revision")
    check(app.score_session.request_model(),
        "Invalid semantic revision permits requesting the correct model")
    deliver_model(app, payload.model)
    check(app.practice_view.stage.renderer.native_ready and app.practice_view.stage.renderer.visible,
        "Valid source model and authentic Verovio assets prepare the production native view")
    check(app.rendered_revision == app.revision and not app.practice_view.start_button.disabled
        and not app.practice_view.stage.score_status_panel.visible,
        "Native readiness enables Play and hides preparation status")
    check(app.commands.size() == 1 and app.commands[0] ==
        {"action":"score_ready","revision":app.revision},
        "Only matching native preparation acknowledges the waiting lesson")
    # Rejecting notation after a successful load must clear the stale success.
    app.commands.clear()
    var unsupported: Dictionary = payload.model.duplicate(true)
    unsupported["notation_events"][0]["note_type"] = "unrenderable"
    check(app.score_session.request_model(),
        "A new model request is needed before a replacement response")
    deliver_model(app, unsupported)
    check(not app.score_error.is_empty() and app.practice_view.stage.score_status_panel.visible,
        "Rejected notation exposes the native preparation failure")
    check(app.practice_view.start_button.disabled and app.rendered_revision != app.revision
        and not app.practice_view.stage.renderer.visible,
        "Rejected notation cannot retain old readiness or display stale ink")
    check(app.commands.is_empty() and app.raster_requests == 0,
        "Rejected notation never acknowledges readiness or falls back to PNG pages")
    for mode in ["practice", "learn"]:
        app.last_state = {"loaded":true,"mode":mode,"phase":"paused","paused":true}
        app._toggle_playing()
        app._toggle_pause()
        check(app.commands.is_empty(), "Keyboard resume cannot bypass a native preparation error: " + mode)
        app.commands.clear()
    app.score_error = ""
    app.last_state = {"loaded":true,"mode":"practice","phase":"paused","paused":true,
        "pause_context":"loading"}
    app._toggle_playing()
    check(app.commands == [{"action":"resume"}], "A paused loading transition can resume while assets prepare")
    app.commands.clear()
    app._retry_score()
    deliver_layout(app, payload.layout)
    deliver_model(app, payload.model)
    check(app.practice_view.stage.renderer.native_ready and not app.practice_view.start_button.disabled
        and app.score_error.is_empty(), "Valid native preparation recovers from failure")
    app.commands.clear()
    var changed := {"loaded":true,"revision":app.revision+1,"phase":"ready",
        "mode":"practice","piece_fingerprint":"native-production-test"}
    app._on_state(0, 200, PackedStringArray(), JSON.stringify(changed).to_utf8_buffer())
    check(not app.practice_view.stage.renderer.native_ready and not app.practice_view.stage.renderer.visible
        and app.practice_view.start_button.disabled and app.practice_view.practice_retry_button.disabled,
        "A new revision immediately clears native ink and disables starting the previous lesson")
    print("NATIVE_PRODUCTION_FAILURES:", failures.size())
    app.queue_free()
    await process_frame
    quit(0 if failures.is_empty() else 1)
