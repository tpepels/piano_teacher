extends "library_application.gd"

# Actual Main/ScoreAssetSession wiring using the app's existing headless UI.
# No HTTP server or score rasterization is needed to verify stale responses.
func run() -> void:
    root.mode = Window.MODE_WINDOWED
    root.size = Vector2i(800, 600)
    var app := OfflineApp.new()
    app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root.add_child(app)
    await process_frame

    var state: Dictionary = saved_state()
    state["revision"] = 7
    state["piece_fingerprint"] = "score-boundary-7"
    state["phase"] = "loading"
    state["awaiting_score_revision"] = 7
    app._on_state(0, 200, PackedStringArray(),
        JSON.stringify(state).to_utf8_buffer())
    check(app.revision == 7 and app.layout_pending,
        "Backend state starts one score layout request through owner")
    var original_id: int = app.score_session.pending_id("layout")
    check(original_id > 0 and app.rendered_revision == -1,
        "No score can publish before the authentic layout is ready")
    app._on_layout(0, 503, PackedStringArray(),
        '{"error":"Layout unavailable"}'.to_utf8_buffer())
    check(app.score_error == "Layout unavailable" and not app.layout_pending,
        "HTTP failure retains a visible score error and clears its request")

    app._retry_score()
    var retry_id: int = app.score_session.pending_id("layout")
    check(retry_id > original_id and app.score_error.is_empty(),
        "Retry starts a fresh request without retaining an old failure")

    var changed: Dictionary = state.duplicate(true)
    changed["revision"] = 8
    changed["piece_fingerprint"] = "score-boundary-8"
    app._on_state(0, 200, PackedStringArray(),
        JSON.stringify(changed).to_utf8_buffer())
    check(app.revision == 8 and app.layout_revision == -1,
        "New score revision invalidates the old renderer")
    app.score_session.complete_response("layout", retry_id, 503,
        '{"error":"Old layout failure"}'.to_utf8_buffer(),
        Time.get_ticks_msec())
    check(app.score_error.is_empty() and app.layout_pending,
        "Stale HTTP failure cannot poison the new revision")
    check(app.score_session.pending_id("layout") > retry_id,
        "Drained stale request triggers the current revision's layout")

    app.free()
    print("SCORE_APPLICATION_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
